"""S4: preview and explicitly confirmed, path-limited workspace commits (offline L3)."""

import fcntl
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from toulmin.adapters.git import git
from toulmin.application.workspace_sync import git_state, machine_local, tracked_notice
from toulmin.core.atomic import digest
from toulmin.core.codec import decode
from toulmin.core.documents import Document, FormatError
from toulmin.core.repository import Repository
from toulmin.protocols.workspace_commit import ChangedPath, CommitSummary, summarize


@dataclass(frozen=True)
class CommitPlan:
    root: Path
    paths: tuple[str, ...]
    digests: tuple[tuple[str, str | None], ...]
    summary: CommitSummary


def _transactions(root: Path) -> None:
    repository = Repository(root)
    projects = root / "projects"
    scopes = (
        [root, *(p for p in projects.iterdir() if p.is_dir() and not p.is_symlink())]
        if projects.is_dir()
        else [root]
    )
    for scope in scopes:
        for name in (".workspace-pending", ".handoff-pending", ".toulmin-new.lock"):
            if os.path.lexists(scope / name):
                raise FormatError(
                    f"{scope / name}: transaction in progress; finish it before committing"
                )
        if scope.name.startswith(".creating-"):
            raise FormatError(f"{scope}: child creation in progress")
        # flock files persist after use, so their presence alone is not a transaction.
        lock = (
            Path(tempfile.gettempdir())
            / f"toulmin-handoff-{os.getuid()}-{digest(str(scope.resolve()).encode())}.lock"
        )
        if lock.exists():
            descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise FormatError(
                        f"{scope}: another proposal/handoff writer holds the lock"
                    ) from error
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        runs = scope / "runs"
        if not runs.is_dir() or runs.is_symlink():
            continue
        records = (
            *runs.glob("proposals/*.outcome.md"),
            *runs.glob("*-build-*-result/import.json"),
            *runs.glob("*-verify-*/verify.json"),
        )
        for path in records:
            path = repository.path(str(path.relative_to(root)), "file")
            if path.name.endswith(".outcome.md"):
                record = decode(path.read_bytes(), str(path)).header
            else:
                record = json.loads(path.read_bytes())
                if not isinstance(record, dict):
                    raise FormatError(f"{path}: invalid transaction record")
            if record.get("disposition") == "applying":
                raise FormatError(f"{path}: transaction applying; finish it before committing")


def _digests(root: Path, paths: tuple[str, ...]) -> tuple[tuple[str, str | None], ...]:
    result = []
    for name in paths:
        path = root / name
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            value = None
        else:
            if stat.S_ISLNK(mode):
                data = b"symlink\0" + os.fsencode(os.readlink(path))
            elif stat.S_ISREG(mode):
                data = str(stat.S_IMODE(mode)).encode() + b"\0" + path.read_bytes()
            else:
                raise FormatError(
                    f"{name}: expected a regular file or symlink, not a nested repository"
                )
            value = digest(data)
        result.append((name, value))
    return tuple(result)


def prepare_commit(root: Path, message: str | None = None) -> CommitPlan:
    root = root.resolve()
    state = git_state(root)
    if state is None:
        raise FormatError(f"{root}: not a git repository")
    if state.error:
        raise FormatError("git: state not read (" + state.error + ")")
    if state.operations or state.unmerged:
        raise FormatError(
            (state.warning or "git operation in progress") + "; finish it before committing"
        )
    _transactions(root)
    tracked = [
        name
        for name in git(root, "ls-files", "-z").stdout.split("\0")
        if name and machine_local(name)
    ]
    candidates = [
        name
        for item in state.changes
        for name in (item.path, item.original)
        if name is not None and machine_local(name)
    ]
    if tracked or candidates:
        advice = (
            tracked_notice(tracked)
            if tracked
            else (
                "Machine-local files are not ignored: add these lines to .gitignore: "
                ".aoe/, tools/*.local.toml"
            )
        )
        raise FormatError(advice + "; machine-local files must stay outside commits")
    # The worktree after `add -A` is the intended content, not an intermediate
    # staged version. This also exposes staged changes outside that final set.
    if state.has_head:
        intended = set(
            filter(
                None,
                git(
                    root,
                    "diff",
                    "HEAD",
                    "--name-only",
                    "-z",
                    "--no-renames",
                    "--no-ext-diff",
                    "--no-textconv",
                ).stdout.split("\0"),
            )
        )
    else:
        intended = {item.path for item in state.changes if os.path.lexists(root / item.path)}
    intended.update(item.path for item in state.changes if item.status == "??")
    paths = tuple(sorted(intended))
    staged = set(
        filter(
            None,
            git(root, "diff", "--cached", "--name-only", "-z", "--no-renames").stdout.split("\0"),
        )
    )
    if outside := staged - set(paths):
        raise FormatError(
            "pre-existing staged changes outside the computed paths: " + ", ".join(sorted(outside))
        )
    if not paths:
        raise FormatError("nothing to commit")
    for name in paths:
        parent = (root / name).parent
        while parent != root:
            if parent.is_symlink():
                raise FormatError(f"{name}: symlink parent; cannot inspect commit content safely")
            parent = parent.parent
    if message is not None and (
        not message.strip() or "\n" in message or "\r" in message or "\0" in message
    ):
        raise FormatError("--message: expected a nonempty, single-line subject")
    records: dict[str, Document] = {}
    for name in paths:
        path = root / name
        parts = path.relative_to(root).parts
        local = parts[2:] if len(parts) > 2 and parts[0] == "projects" else parts
        is_record = (
            path.name.endswith(".outcome.md")
            and local[:2] == ("runs", "proposals")
            or bool(local)
            and local[0] in {"sessions", "handoffs"}
            or bool(local)
            and local[0] == "proposals"
            and path.name == "receipt.md"
        )
        if is_record and path.suffix == ".md" and path.is_file() and not path.is_symlink():
            try:
                records[name] = decode(path.read_bytes(), name)
            except ValueError:
                # A plain-text handoff carries no machine-readable outcome.
                pass
    created = {item.path: item.status in {"??", "A ", "AM"} for item in state.changes}
    changes = tuple(ChangedPath(name, created.get(name, False)) for name in paths)
    return CommitPlan(root, paths, _digests(root, paths), summarize(changes, records, message))


def confirm_commit(plan: CommitPlan) -> str:
    # A concurrent edit between this command's computation and staging must not silently
    # broaden the approved set. A later independent preview is not an approval token.
    current = prepare_commit(plan.root, plan.summary.message.splitlines()[0])
    if current.paths != plan.paths or current.digests != plan.digests:
        raise FormatError("workspace changed while preparing the commit; run the command again")
    # Check identity before staging so a missing author leaves the index untouched;
    # a failing hook can still leave the computed paths staged (git reports it).
    git(plan.root, "var", "GIT_AUTHOR_IDENT")
    git(plan.root, "var", "GIT_COMMITTER_IDENT")
    with tempfile.TemporaryDirectory(prefix="toulmin-commit-") as temporary:
        paths_file = Path(temporary) / "paths"
        message_file = Path(temporary) / "message"
        paths_file.write_bytes(b"\0".join(os.fsencode(path) for path in plan.paths) + b"\0")
        message_file.write_text(plan.summary.message, encoding="utf-8")
        pathspec = ("--pathspec-from-file=" + str(paths_file), "--pathspec-file-nul")
        indexed = set(git(plan.root, "ls-files", "-z").stdout.split("\0"))
        # A deletion already staged by `git mv`/`git rm` no longer matches add's
        # index/worktree pathspecs. It stays in the preview and commit path set.
        add_paths = tuple(
            name for name in plan.paths if name in indexed or os.path.lexists(plan.root / name)
        )
        if add_paths:
            staging_file = Path(temporary) / "stage-paths"
            staging_file.write_bytes(b"\0".join(os.fsencode(name) for name in add_paths) + b"\0")
            git(
                plan.root,
                "add",
                "-A",
                "--pathspec-from-file=" + str(staging_file),
                "--pathspec-file-nul",
            )
        git(plan.root, "commit", "-F", str(message_file), *pathspec, timeout=600)
    return git(plan.root, "rev-parse", "HEAD").stdout.strip()
