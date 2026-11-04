import json
import os
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from toulmin.cli import initialize as scaffolding
from toulmin.cli.app import app

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[2]


def invoke(root, project="demo"):
    return runner.invoke(app, ["init", str(root), "--project", project])


def snapshot(root):
    """Record regular files and links, including Git, without following links."""
    result = {}
    if not root.exists():
        return result
    for path in root.rglob("*"):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = (str(path.readlink()), path.lstat().st_mtime_ns)
        elif path.is_file():
            result[relative] = (path.read_bytes(), path.stat().st_mtime_ns)
        else:
            result[relative] = "directory"
    return result


def test_init_creates_complete_template_and_git_without_commit(tmp_path):
    root = tmp_path / "research"
    result = invoke(root)
    assert result.exit_code == 0, result.output
    for directory in (
        "framework",
        "roles",
        "global/papers",
        "global/assumptions",
        "global/calibration",
        "tools",
        "projects/demo/claims",
        "projects/demo/evidence",
        "projects/demo/objections",
        "projects/demo/decisions",
        "projects/demo/explorations",
        "projects/demo/specs",
        "projects/demo/runs",
        "projects/demo/sessions",
    ):
        assert (root / directory).is_dir(), directory
    assert (root / "CLAUDE.md").is_symlink()
    assert (root / "CLAUDE.md").readlink() == Path("AGENTS.md")
    assert json.loads((root / ".gemini/settings.json").read_text()) == {
        "context": {"fileName": "AGENTS.md"}
    }
    project = (root / "projects/demo/PROJECT.md").read_text()
    header = YAML(typ="safe").load(project.split("---")[1])
    assert header == {
        "schema_version": 1,
        "project": "demo",
        "stage": "explore",
        "recent_decisions": [],
        "next_step": "Describe the research goal and write the first proposed Claim.",
        "last_handoff": None,
    }
    assert len(project.splitlines()) <= 40
    assert "## Goal" in project and "## Constraints" in project
    assert "{{project}}" not in project
    for section in (
        "Problem",
        "Why now",
        "Magnitude",
        "Closest prior work",
        "Objections and responses",
        "Kill criteria",
        "Minimal validation experiment",
    ):
        assert f"## {section}" in (root / "projects/demo/brief.md").read_text()
    assert (root / ".git/HEAD").read_text() == "ref: refs/heads/main\n"
    assert not (root / ".git/refs/heads/main").exists()
    for path in root.rglob(".gitkeep"):
        check = subprocess.run(
            ["git", "-C", str(root), "check-ignore", str(path)], capture_output=True, check=False
        )
        assert check.returncode == 1


def test_workspace_rules_and_role_contracts_are_independent_of_development(tmp_path):
    root = tmp_path / "research"
    assert invoke(root).exit_code == 0
    rules = (root / "AGENTS.md").read_text()
    assert rules != (ROOT / "AGENTS.md").read_text()
    assert "PROGRESS.md" not in rules and "TODO.md" not in rules
    for phrase in ("Entry protocol", "Exit protocol", "last_handoff", "researcher confirmation"):
        assert phrase in rules
    roles = sorted(path.stem for path in (root / "roles").glob("*.md"))
    assert roles == [
        "crossval",
        "reviewer",
        "reviewer-industry",
        "reviewer-skeptic",
        "reviewer-theorist",
        "reviewer-why-not-x",
        "scribe",
        "synthesizer",
    ]
    for role in roles:
        text = (root / "roles" / f"{role}.md").read_text()
        for field in (
            "Operation:",
            "Inputs:",
            "Excluded inputs:",
            "Permissions:",
            "Output:",
            "Prohibitions:",
            "Completion:",
        ):
            assert field in text


@pytest.mark.parametrize(
    "name", ["formats.md", "format-examples.md", "protocols.md", "workspace-formats.md"]
)
def test_packaged_framework_contracts_match_canonical_documents(name):
    assert (ROOT / "src/toulmin/cli/templates/framework" / name).read_bytes() == (
        ROOT / "docs" / name
    ).read_bytes()


def test_repeated_init_is_a_byte_and_mtime_noop(tmp_path):
    root = tmp_path / "research"
    assert invoke(root).exit_code == 0
    before = snapshot(root)
    result = invoke(root)
    assert result.exit_code == 0, result.output
    assert "created entries: 0" in result.stdout
    assert snapshot(root) == before


def test_new_project_preserves_prior_project_edits_and_global_files(tmp_path):
    root = tmp_path / "research"
    assert invoke(root).exit_code == 0
    previous = root / "projects/demo/PROJECT.md"
    previous.write_text(previous.read_text().replace("stage: explore", "stage: critique"))
    before = snapshot(root)
    assert invoke(root, "second-project").exit_code == 0
    after = snapshot(root)
    assert all(after[path] == content for path, content in before.items())
    assert (root / "projects/second-project/PROJECT.md").is_file()
    assert "project: second-project" in (root / "projects/second-project/PROJECT.md").read_text()


@pytest.mark.parametrize(
    "relative", ["AGENTS.md", "projects/demo/brief.md", ".gemini/settings.json"]
)
def test_conflicts_are_detected_before_any_writes(tmp_path, relative):
    root = tmp_path / "research"
    collision = root / relative
    collision.parent.mkdir(parents=True)
    collision.write_text("Researcher's existing file.\n")
    before = snapshot(root)
    result = invoke(root)
    assert result.exit_code == 1
    assert "Conflicting file" in result.stderr
    assert result.stdout == ""
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "relative", ["projects", "projects/demo/claims", "AGENTS.md", "CLAUDE.md", ".git"]
)
def test_foreign_or_dangling_symlinks_are_rejected_without_changes(tmp_path, relative):
    root = tmp_path / "research"
    outside = tmp_path / "outside"
    outside.mkdir()
    target = root / relative
    target.parent.mkdir(parents=True)
    target.symlink_to(outside / "missing" if relative == "AGENTS.md" else outside)
    before = snapshot(root)
    outside_before = snapshot(outside)
    result = invoke(root)
    assert result.exit_code == 1
    assert snapshot(root) == before
    assert snapshot(outside) == outside_before


def test_symlink_in_root_ancestor_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside)
    assert invoke(alias / "research").exit_code == 1
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("project", ["../escape", "/absolute", "a/b", "Demo", "a--b"])
def test_bad_project_names_do_not_write_files(tmp_path, project):
    root = tmp_path / "research"
    assert invoke(root, project).exit_code == 2
    assert not root.exists()


def test_dotdot_in_root_is_rejected(tmp_path):
    assert invoke(tmp_path / "research/../escape").exit_code == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("relative", ["CLAUDE.md", "projects", ".git"])
def test_wrong_entry_types_fail_without_changes(tmp_path, relative):
    root = tmp_path / "research"
    root.mkdir()
    (root / relative).write_text("existing\n")
    before = snapshot(root)
    assert invoke(root).exit_code == 1
    assert snapshot(root) == before


def test_symlink_creation_failure_rolls_back_new_tree(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("symlinks unavailable")

    monkeypatch.setattr(Path, "symlink_to", fail)
    root = tmp_path / "nested/research"
    result = invoke(root)
    assert result.exit_code == 1
    assert "symlinks unavailable" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_publishing_failure_preserves_existing_tree(tmp_path, monkeypatch):
    root = tmp_path / "research"
    assert invoke(root).exit_code == 0
    before = snapshot(root)
    original = os.link
    count = 0

    def fail_second(source, destination):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("disk full")
        original(source, destination)

    monkeypatch.setattr(os, "link", fail_second)
    result = invoke(root, "second")
    assert result.exit_code == 1
    assert "disk full" in result.stderr
    assert snapshot(root) == before


def test_git_copy_failure_rolls_back_including_partial_metadata(tmp_path, monkeypatch):
    def fail(source, destination, **kwargs):
        (destination / "partial").write_text("incomplete")
        raise OSError("Git metadata copy failed")

    monkeypatch.setattr(scaffolding.shutil, "copytree", fail)
    root = tmp_path / "research"
    assert invoke(root).exit_code == 1
    assert list(tmp_path.iterdir()) == []


def test_missing_git_leaves_no_scaffold(tmp_path, monkeypatch):
    root = tmp_path / "research"
    monkeypatch.setattr(scaffolding.shutil, "which", lambda name: None)
    assert invoke(root).exit_code == 1
    assert not root.exists()


def test_git_failure_leaves_no_scaffold(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("Git initialization failed")

    monkeypatch.setattr(scaffolding, "_run_git", fail)
    assert invoke(tmp_path / "research").exit_code == 1
    assert list(tmp_path.iterdir()) == []


def test_git_environment_cannot_redirect_init_or_install_user_templates(tmp_path, monkeypatch):
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.setenv("GIT_DIR", str(unrelated / "redirected.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(unrelated))
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(unrelated))
    root = tmp_path / "research"
    assert invoke(root).exit_code == 0
    assert (root / ".git/HEAD").exists()
    assert not (root / ".git/hooks").exists()
    assert list(unrelated.iterdir()) == []


def test_creation_race_never_overwrites_the_other_writers_file(tmp_path, monkeypatch):
    root = tmp_path / "research"
    original = os.link
    inserted = False

    def race(source, destination):
        nonlocal inserted
        if not inserted:
            inserted = True
            destination.write_text("other writer\n")
        original(source, destination)

    monkeypatch.setattr(os, "link", race)
    result = invoke(root)
    assert result.exit_code == 1
    files = [path for path in root.rglob("*") if path.is_file()]
    assert len(files) == 1
    assert files[0].read_text() == "other writer\n"
    assert {path for path in root.rglob("*") if path.is_dir()} == {
        parent for parent in files[0].parents if parent != root and parent.is_relative_to(root)
    }
    assert not (root / ".git").exists()


def test_init_inside_parent_git_creates_an_independent_repository(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    subprocess.run(["git", "init", "--quiet", str(parent)], check=True)
    before = snapshot(parent / ".git")
    root = parent / "research"
    assert invoke(root).exit_code == 0
    assert (root / ".git/HEAD").exists()
    assert snapshot(parent / ".git") == before


def test_missing_required_arguments_are_usage_errors(tmp_path):
    # WI2: init ROOT without --project creates a workspace; only ROOT is required.
    result = runner.invoke(app, ["init", "--project", "demo"])
    assert result.exit_code == 2
    assert list(tmp_path.iterdir()) == []
