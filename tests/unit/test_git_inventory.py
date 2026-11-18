"""MI1: bounded real Git listings and subprocess lifecycle; temporary sources only."""

import json
import os
import subprocess
import sys
import time

import pytest

from tests.acceptance.wo_support import git, repository
from toulmin.application import git_inventory
from toulmin.application.sources import inspect_source, inspect_source_v2
from toulmin.core.documents import FormatError
from toulmin.core.sources import InspectionPolicy


def test_large_git_listing_is_bounded_and_selection_reaches_late_component(tmp_path):
    source = repository(tmp_path / "source")
    bulk = source / ("a" * 230) / ("b" * 230) / ("c" * 230)
    bulk.mkdir(parents=True)
    for index in range(3_300):
        (bulk / f"{index:05}.md").write_text("bulk\n")
    component = source / "z-component"
    component.mkdir()
    (component / "README.md").write_text("Selected component\n")
    (component / "main.py").write_text("def run(): return 1\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "large source fixture")
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=source)
    assert len(raw) > 2_000_000
    index_before = (source / ".git/index").read_bytes()
    before = git(source, "rev-parse", "HEAD")
    unscoped = inspect_source_v2(tmp_path / "records", source)
    assert json.loads(unscoped.inventory)["truncated"] is True
    policy = InspectionPolicy(("z-component/README.md", "z-component/main.py"), ())
    selected = inspect_source_v2(tmp_path / "records", source, inspection=policy)
    value = json.loads(selected.inventory)
    assert [item["path"] for item in value["files"]] == [
        "z-component/README.md",
        "z-component/main.py",
    ]
    assert not value["truncated"]
    assert selected.identity == unscoped.identity
    assert "ordered literal" in value["coverage"]
    assert git(source, "rev-parse", "HEAD") == before
    assert (source / ".git/index").read_bytes() == index_before
    assert git(source, "status", "--porcelain") == ""


@pytest.mark.parametrize("pathspec_env", [None, *sorted(git_inventory.PATHSPEC_ENV)])
def test_include_priority_and_literal_exclusion_do_not_follow_globs(
    tmp_path, monkeypatch, pathspec_env
):
    source = repository(tmp_path / "source")
    (source / "component").mkdir()
    for name in ("main.py", "omit.py", "second.py"):
        (source / "component" / name).write_text(name)
    (source / "priority.md").write_text("first\n")
    policy = InspectionPolicy(("priority.md", "component"), ("component/omit.py",))
    if pathspec_env is not None:
        monkeypatch.setenv(pathspec_env, "1")
    observed = inspect_source(tmp_path / "records", source, inspection=policy)
    names = [item["path"] for item in json.loads(observed.inventory)["files"]]
    assert names == ["priority.md", "component/main.py", "component/second.py"]


def fake_git(tmp_path, monkeypatch, body):
    folder = tmp_path / "bin"
    folder.mkdir()
    script = folder / "git"
    script.write_text(f"#!{sys.executable}\n" + body)
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(folder) + os.pathsep + os.environ["PATH"])


def test_candidate_budget_terminates_and_reaps_git(tmp_path, monkeypatch):
    pidfile = tmp_path / "child.pid"
    fake_git(
        tmp_path,
        monkeypatch,
        "import os,sys,time\nfrom pathlib import Path\n"
        f"Path({str(pidfile)!r}).write_text(str(os.getpid()))\n"
        "sys.stdout.buffer.write(b'a.md\\0b.md\\0c.md\\0');sys.stdout.flush()\n"
        "time.sleep(30)\n",
    )
    monkeypatch.setattr(git_inventory, "MAX_CANDIDATES", 2)
    started = time.monotonic()
    result = git_inventory.git_paths(tmp_path, None, started + 5)
    assert result.paths == ("a.md", "b.md") and result.truncated
    assert time.monotonic() - started < 5
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_deadline_keeps_only_complete_records_and_reaps_git(tmp_path, monkeypatch):
    fake_git(
        tmp_path,
        monkeypatch,
        "import sys,time\n"
        "sys.stdout.buffer.write(b'complete.md\\0partial');sys.stdout.flush()\n"
        "time.sleep(30)\n",
    )
    result = git_inventory.git_paths(tmp_path, None, time.monotonic() + 0.3)
    assert result.paths == ("complete.md",) and result.truncated


def test_failed_git_is_not_a_successful_partial_inventory(tmp_path, monkeypatch):
    fake_git(
        tmp_path, monkeypatch, "import sys\nsys.stdout.buffer.write(b'file.md\\0');sys.exit(7)\n"
    )
    with pytest.raises(FormatError, match="inventory failed"):
        git_inventory.git_paths(tmp_path, None, time.monotonic() + 5)


def test_git_discovery_failure_in_subdirectory_cannot_become_directory_source(
    tmp_path, monkeypatch
):
    from toulmin.application import sources

    source = repository(tmp_path / "source")
    child = source / "component"
    child.mkdir()
    monkeypatch.setattr(sources, "_git", lambda *args: None)
    with pytest.raises(FormatError, match="Git discovery unavailable"):
        sources.inspect_source(tmp_path / "records", child)
