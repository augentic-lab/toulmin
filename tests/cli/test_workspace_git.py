"""S4: offline git advice and explicit commits, using disposable repositories only."""

import json
import os
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from toulmin.adapters import git as git_adapter
from toulmin.adapters.base import Finished
from toulmin.application import workspace_sync
from toulmin.application.aoe import render_scope, scope_state
from toulmin.application.workspace_commit import confirm_commit, prepare_commit
from toulmin.application.workspace_sync import git_state
from toulmin.cli import decide, entry
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.atomic import handoff_mutex
from toulmin.core.codec import encode
from toulmin.core.documents import Document, FormatError
from toulmin.protocols.workspace_commit import ChangedPath, summarize


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def write(root, name, text="fixture\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def snapshot(root):
    return {
        str(path.relative_to(root)): os.readlink(path) if path.is_symlink() else path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }


@pytest.fixture(autouse=True)
def git_environment(tmp_path, monkeypatch):
    # Deliberately use a temporary global config: production commit must inherit it,
    # including identity and hooks, rather than force GIT_CONFIG_GLOBAL=/dev/null.
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n name = Fixture\n email = fixture@example.invalid\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "workspace with spaces"
    initialize_workspace(root, "Sync fixture")
    seed = tmp_path / "project-template"
    initialize(seed, "demo")
    shutil.copytree(seed / "projects/demo", root / "projects/demo")
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    git(root, "add", "-A")
    git(root, "commit", "-m", "Initial fixture")
    return root


@pytest.fixture
def upstream(root, tmp_path):
    bare = tmp_path / "remote.git"
    git(root, "init", "--bare", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-u", "origin", "main")
    peer = tmp_path / "peer"
    git(root, "clone", "--quiet", "--branch", "main", str(bare), str(peer))
    return bare, peer


def advance(root, name):
    write(root, name)
    git(root, "add", "--", name)
    git(root, "commit", "-m", name)


def change_tracking(root, upstream, mode):
    if mode in {"ahead", "diverged"}:
        advance(root, "local.txt")
    if mode in {"behind", "diverged"}:
        advance(upstream[1], "peer.txt")
        git(upstream[1], "push", "origin", "main")
        git(root, "fetch", "--quiet", "origin")  # local bare repository only


def run(root, *args):
    return CliRunner().invoke(app, [*args, "--root", str(root)])


def test_clean_no_upstream_never_fetched_and_dirty_counts(root):
    before = snapshot(root)
    state = git_state(root)
    assert state.line() == "git: main, 0 uncommitted files, no upstream (never fetched)"
    assert state.warning is None and snapshot(root) == before
    write(root, "file with spaces.txt")
    write(root, "中文.txt")
    write(root, ".aoe/binding.json")
    write(root, "tools/chief.local.toml")
    write(root, "projects/demo/.aoe/binding.json")
    assert "2 uncommitted files" in git_state(root).line()


@pytest.mark.parametrize(
    "mode,counts", [("clean", (0, 0)), ("ahead", (1, 0)), ("behind", (0, 1)), ("diverged", (1, 1))]
)
def test_tracking_from_local_refs_only(root, upstream, mode, counts, monkeypatch):
    change_tracking(root, upstream, mode)
    if mode in {"behind", "diverged"}:
        os.utime(root / ".git/FETCH_HEAD", (1000, 1000))
        monkeypatch.setattr(workspace_sync.time, "time", lambda: 8200)
    before = snapshot(root)
    state = git_state(root)
    assert (state.ahead, state.behind) == counts and state.upstream == "origin/main"
    assert f"{counts[0]} ahead / {counts[1]} behind origin/main" in state.line()
    assert ("last fetch 2 h ago" if counts[1] else "never fetched") in state.line()
    if mode == "behind":
        assert state.warning == "pull before writing: git pull --ff-only"
    elif mode == "diverged":
        assert state.warning == (
            "diverged from origin/main: reconcile before writing; "
            "never merge histories that both created objects"
        )
    else:
        assert state.warning is None
    assert snapshot(root) == before


def test_detached_head(root):
    git(root, "checkout", "--detach", "HEAD")
    assert "detached HEAD" in git_state(root).line()


@pytest.mark.parametrize(
    "marker,label",
    [("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("CHERRY_PICK_HEAD", "cherry-pick")],
)
def test_in_progress_state_and_commit_refusal(root, marker, label):
    write(root, ".git/" + marker, git(root, "rev-parse", "HEAD"))
    write(root, "changed.txt")
    before = snapshot(root)
    assert label + " in progress" in git_state(root).line()
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and label + " in progress" in result.output
    assert snapshot(root) == before


def make_conflict(root):
    write(root, "conflict.txt", "base\n")
    git(root, "add", "conflict.txt")
    git(root, "commit", "-m", "base")
    git(root, "checkout", "-b", "other")
    write(root, "conflict.txt", "other\n")
    git(root, "commit", "-am", "other")
    git(root, "checkout", "main")
    write(root, "conflict.txt", "main\n")
    git(root, "commit", "-am", "main")
    result = subprocess.run(["git", "-C", str(root), "merge", "other"], capture_output=True)
    assert result.returncode == 1


def test_unmerged_paths_refuse_without_writes_even_without_merge_marker(root):
    make_conflict(root)
    (root / ".git/MERGE_HEAD").unlink()
    before = snapshot(root)
    assert git_state(root).unmerged
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "unmerged paths" in result.output
    assert snapshot(root) == before


@pytest.mark.parametrize("scope", [None, "demo"])
def test_status_and_open_notices_include_git_state(root, scope, monkeypatch):
    args = ["status", *([scope] if scope else [])]
    result = run(root, *args)
    assert result.exit_code == 0 and "git: main, 0 uncommitted files" in result.output
    assert "git: main, 0 uncommitted files" in render_scope(scope_state(root, scope))
    monkeypatch.setattr(entry, "note", lambda _: None)
    monkeypatch.setattr(entry, "_pending", lambda _: None)
    monkeypatch.setattr(
        entry,
        "open_scope",
        lambda base, child, *a, **kw: print(render_scope(scope_state(base, child))),
    )
    opened = run(root, "open", *([scope] if scope else []))
    assert opened.exit_code == 0 and "git: main, 0 uncommitted files" in opened.output


@pytest.mark.parametrize("mode", ["clean", "ahead", "behind", "diverged", "merge"])
def test_decide_only_prints_warnings_before_first_item(root, upstream, mode, monkeypatch):
    change_tracking(root, upstream, mode)
    if mode == "merge":
        write(root, ".git/MERGE_HEAD", git(root, "rev-parse", "HEAD"))
    monkeypatch.setattr(
        decide, "inventory", lambda _: decide.Inventory((decide.Item("object", "fixture"),), 0)
    )
    monkeypatch.setattr(decide, "_interactive", lambda: False)
    result = run(root, "decide")
    assert result.exit_code == 0 and "git: main" not in result.output
    assert ("Warning:" in result.output) == (mode in {"behind", "diverged", "merge"})
    if "Warning:" in result.output:
        assert result.output.index("Warning:") < result.output.index("Object draft: fixture")


def test_git_failure_never_fails_status_open_or_decide(root, monkeypatch):
    def fail(*args, **kwargs):
        return Finished(128, "", "fixture git failure\n", 0)

    monkeypatch.setattr(git_adapter, "run_process", fail)
    result = run(root, "status")
    assert result.exit_code == 0 and "git: state not read (" in result.output
    assert "fixture git failure" in render_scope(scope_state(root, None))
    result = run(root, "decide")
    assert result.exit_code == 0 and "Warning:" not in result.output
    assert "git: state not read (" in result.output


def test_no_git_no_state_line_and_commit_refuses(root):
    (root / ".git").rename(root / "saved-git")
    assert git_state(root) is None
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "not a git repository" in result.output
    assert snapshot(root) == before


def research_changes(root):
    claim = "projects/demo/claims/C-001.md"
    spec = "projects/demo/specs/S-001.md"
    outcome = "projects/demo/runs/proposals/ruling-fixture.outcome.md"
    for path, header in (
        (claim, {"id": "C-001", "status": "proposed"}),
        (spec, {"id": "S-001", "status": "passed"}),
        (outcome, {"kind": "proposal-outcome", "disposition": "applied"}),
    ):
        write(root, path, encode(Document(header, "Fixture record.\n")).decode())
    write(root, "projects/demo/runs/fixture/output.md")
    write(root, "projects/demo/runs/fixture/environment.txt")
    write(
        root,
        "projects/demo/sessions/fixture.md",
        encode(Document({"kind": "session"}, "Fixture.\n")).decode(),
    )
    write(root, "WORKSPACE.md", (root / "WORKSPACE.md").read_text() + "\nFixture note.\n")
    return claim, spec, outcome


def test_commit_preview_grouping_message_and_subject_override(root):
    claim, spec, outcome = research_changes(root)
    before = snapshot(root)
    result = run(root, "commit")
    assert result.exit_code == 0, result.output
    for value in (
        "Objects created — demo",
        "C-001",
        "S-001",
        "Proposal outcomes",
        "Run archives (1)",
        "Sessions / handoffs",
        "Other workspace files",
        "Applied outcome: " + outcome,
        "Objects created: C-001, S-001",
        "Nothing is committed without --confirm. Toulmin never pushes: run git push yourself.",
    ):
        assert value in result.output
    custom = run(root, "commit", "--message", "Reviewed fixture results")
    assert "Proposed message:\nReviewed fixture results\n\n" in custom.output
    assert "Applied outcome: " + outcome in custom.output and snapshot(root) == before
    git(root, "add", claim, spec)
    git(root, "commit", "-m", "prior objects")
    write(root, claim, (root / claim).read_text() + "\nMore.\n")
    assert "Objects changed — demo" in run(root, "commit").output


def test_summary_is_pure_and_uses_only_supplied_records():
    changes = (
        ChangedPath("projects/demo/specs/S-001.md"),
        ChangedPath("projects/demo/decisions/D-004.md", True),
    )
    summary = summarize(
        changes,
        {"projects/demo/specs/S-001.md": Document({"status": "passed"}, "ignore worker prose")},
    )
    assert "S-001" in summary.message and "D-004" in summary.message
    assert "passed" not in summary.message
    assert (
        "Objects changed: S-001" in summary.message and "Objects created: D-004" in summary.message
    )
    assert "ignore worker prose" not in summary.message


def test_nothing_to_commit_refuses_without_writes(root):
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "nothing to commit" in result.output
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "path", [".aoe/binding.json", "projects/demo/.aoe/binding.json", "tools/chief.local.toml"]
)
@pytest.mark.parametrize("tracked", [True, False])
def test_machine_local_files_refuse_without_writes(root, path, tracked):
    write(root, path)
    if tracked:
        git(root, "add", "-f", "--", path)
    else:
        (root / ".gitignore").write_text("")
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert (
        result.exit_code == 1 and "machine-local files must stay outside commits" in result.output
    )
    assert ("git rm -r --cached" if tracked else "add these lines to .gitignore") in result.output
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "marker",
    [
        ".workspace-pending",
        "projects/demo/.handoff-pending",
        "projects/demo/.toulmin-new.lock",
        "projects/.creating-demo",
    ],
)
def test_transaction_markers_refuse_without_writes(root, marker):
    (root / marker).mkdir()
    write(root, "changed.txt")
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and (
        "in progress" in result.output or "transaction" in result.output
    )
    assert snapshot(root) == before


@pytest.mark.parametrize("filename", ["fixture.outcome.md", "import.json", "verify.json"])
def test_applying_records_refuse_without_writes(root, filename):
    record = {"disposition": "applying"}
    text = (
        encode(Document(record, "Interrupted fixture.\n")).decode()
        if filename.endswith(".md")
        else json.dumps(record)
    )
    folder = (
        "proposals"
        if filename.endswith(".md")
        else "20261111T120000Z-build-S-001-result"
        if filename == "import.json"
        else "20261111T120000Z-verify-S-001"
    )
    write(root, f"projects/demo/runs/{folder}/{filename}", text)
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "transaction applying" in result.output
    assert snapshot(root) == before


def test_active_proposal_writer_refuses_but_idle_flock_file_does_not(root):
    write(root, "changed.txt")
    with handoff_mutex(root / "projects/demo"):
        before = snapshot(root)
        result = run(root, "commit", "--confirm")
        assert result.exit_code == 1 and "holds the lock" in result.output
        assert snapshot(root) == before
    assert prepare_commit(root).paths == ("changed.txt",)


def test_staged_outside_computed_set_refuses(root):
    write(root, "outside.txt")
    git(root, "add", "outside.txt")
    (root / "outside.txt").unlink()
    write(root, "included.txt")
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "pre-existing staged changes outside" in result.output
    assert snapshot(root) == before


def test_confirm_commits_exact_paths_with_spaces_unicode_renames_and_deletions(root, upstream):
    advance(root, "old name.txt")
    git(root, "mv", "old name.txt", "renamed 文件.txt")
    (root / "roles/reviewer.md").unlink()
    write(root, "new 文件.txt")
    write(root, ":(glob)* literal.txt")
    write(root, "--leading-option.txt")
    write(root, ".aoe/binding.json")
    paths = set(prepare_commit(root).paths)
    remote = git(upstream[0], "rev-parse", "refs/heads/main")
    result = run(root, "commit", "--message", "Preserve fixture", "--confirm")
    assert result.exit_code == 0, result.output
    assert "Committed: " + git(root, "rev-parse", "HEAD").strip() in result.output
    assert "Push yourself: git push" in result.output
    committed = set(
        filter(
            None,
            git(
                root,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "-z",
                "--no-renames",
                "HEAD",
            ).split("\0"),
        )
    )
    assert committed == paths
    assert not git(root, "status", "--porcelain=v1")
    assert git(root, "log", "-1", "--format=%s").strip() == "Preserve fixture"
    assert git(upstream[0], "rev-parse", "refs/heads/main") == remote


def test_first_commit_and_normal_global_identity(root, tmp_path):
    first = tmp_path / "fresh"
    initialize_workspace(first, "New fixture")
    result = run(first, "commit", "--confirm")
    assert result.exit_code == 0, result.output
    assert (
        git(first, "log", "-1", "--format=%an <%ae>").strip() == "Fixture <fixture@example.invalid>"
    )


def test_hook_failure_is_verbatim_exit_status_and_never_retried(root):
    write(root, "changed.txt")
    hook = write(
        root,
        ".git/hooks/pre-commit",
        "#!/bin/sh\nprintf 'HOOK SENTINEL: human intervention required\\n' >&2\n"
        "echo x >> .git/hook-calls\nexit 23\n",
    )
    hook.chmod(0o755)
    head = git(root, "rev-parse", "HEAD")
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1  # git commit reports a failing hook as status 1
    assert "HOOK SENTINEL: human intervention required\n" in result.output
    assert (root / ".git/hook-calls").read_text() == "x\n"
    assert git(root, "rev-parse", "HEAD") == head


def test_identity_failure_is_reported_with_git_status(root, monkeypatch):
    write(root, "changed.txt")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "user.useConfigOnly")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    head = git(root, "rev-parse", "HEAD")
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 128 and "Author identity unknown" in result.output
    assert git(root, "rev-parse", "HEAD") == head
    assert git(root, "diff", "--cached", "--name-only") == ""  # nothing staged


def test_edit_after_computation_refuses_without_staging(root):
    write(root, "changed.txt")
    plan = prepare_commit(root)
    write(root, "changed.txt", "edited after preview\n")
    before = snapshot(root)
    with pytest.raises(FormatError, match="workspace changed"):
        confirm_commit(plan)
    assert snapshot(root) == before


def test_confirm_preserves_research_body_when_subject_is_overridden(root):
    _, _, outcome = research_changes(root)
    result = run(root, "commit", "--message", "Reviewed results", "--confirm")
    assert result.exit_code == 0, result.output
    message = git(root, "log", "-1", "--format=%B")
    assert message.startswith("Reviewed results\n\ndemo:\n")
    assert "Objects created: C-001, S-001" in message
    assert "Applied outcome: " + outcome in message
    assert "Session/handoff: projects/demo/sessions/fixture.md" in message


def test_clean_tracked_machine_file_and_renamed_source_are_both_refused(root):
    write(root, "tools/chief.local.toml")
    git(root, "add", "-f", "tools/chief.local.toml")
    git(root, "commit", "-m", "Previously tracked machine setting")
    write(root, "changed.txt")
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "git rm -r --cached" in result.output
    assert snapshot(root) == before
    git(root, "mv", "tools/chief.local.toml", "portable.txt")
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "machine-local files" in result.output
    assert snapshot(root) == before


def test_worker_data_that_looks_like_a_journal_is_not_a_transaction(root):
    write(root, "projects/demo/runs/raw-worker/import.json", '{"disposition": "applying"}')
    write(root, "projects/demo/runs/raw-worker/worker.outcome.md", "worker data, not a proposal")
    plan = prepare_commit(root)
    assert len(plan.paths) == 2
    assert tuple(group for group, _ in plan.summary.groups) == ("Run archives (1)",)


@pytest.mark.parametrize("message", ["", "two\nlines", "two\rlines"])
def test_invalid_subject_refuses_without_writes(root, message):
    write(root, "changed.txt")
    before = snapshot(root)
    result = run(root, "commit", "--message", message, "--confirm")
    assert result.exit_code == 1 and "single-line subject" in result.output
    assert snapshot(root) == before


def test_new_unrelated_paths_since_an_earlier_preview_are_recomputed(root):
    write(root, "first.txt")
    assert run(root, "commit").exit_code == 0
    write(root, "second.txt")
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 0, result.output
    assert set(git(root, "show", "--format=", "--name-only", "HEAD").splitlines()) == {
        "first.txt",
        "second.txt",
    }


def test_commit_does_not_follow_a_replaced_directory_symlink(root, tmp_path):
    write(root, "previous/file.md")
    git(root, "add", "previous/file.md")
    git(root, "commit", "-m", "Tracked directory fixture")
    shutil.rmtree(root / "previous")
    outside = tmp_path / "outside"
    outside.mkdir()
    write(outside, "file.md", "Outside fixture must not be read or changed.\n")
    (root / "previous").symlink_to(outside, target_is_directory=True)
    before = snapshot(root)
    result = run(root, "commit", "--confirm")
    assert result.exit_code == 1 and "symlink parent" in result.output
    assert snapshot(root) == before
