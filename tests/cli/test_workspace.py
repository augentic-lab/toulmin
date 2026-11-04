"""WI2: project-free initialization and offline workspace status (CLI boundary)."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.application.workspace import WorkspaceService
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize
from toulmin.core.atomic import digest
from toulmin.core.documents import FormatError

runner = CliRunner()
DOCS = Path(__file__).resolve().parents[2] / "docs"
# The contract's initial WORKSPACE.md example (docs/workspace-formats.md, section 4).
CONTRACT_INITIAL_SHA256 = "3a9d405abca38945ad12898f8e3b61c79e012bc310671de496ac8e4d366d6793"


def init(root, *extra):
    return runner.invoke(app, ["init", str(root), *extra])


def status(root, *extra):
    return runner.invoke(app, ["status", *extra, "--root", str(root)])


def snapshot(root):
    """Bytes and mtimes of every entry, without following links."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = (os.readlink(path), path.lstat().st_mtime_ns)
        elif path.is_file():
            result[relative] = (path.read_bytes(), path.stat().st_mtime_ns)
        else:
            result[relative] = "directory"
    return result


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "serving"
    assert init(root, "--name", "Serving Research").exit_code == 0
    return root


def add_child(root, name="scheduling"):
    """A synthetic prepared child: the project template copied in place (not WI6 creation)."""
    legacy = root.parent / f"template-{name}"
    initialize(legacy, name)
    shutil.copytree(legacy / "projects" / name, root / "projects" / name)
    return root / "projects" / name


def write_charter(root, header_lines, body):
    text = "---\nschema_version: 1\n" + "".join(f"{line}\n" for line in header_lines) + "---\n"
    (root / "WORKSPACE.md").write_text(text + body)


def test_init_creates_workspace_only_state_without_child_or_model(workspace):
    root = workspace
    assert digest((root / "WORKSPACE.md").read_bytes()) == CONTRACT_INITIAL_SHA256
    assert sorted(path.name for path in (root / "projects").iterdir()) == [".gitkeep"]
    for directory in ("runs/drafts", "sessions", "shared/resources", "framework", "roles"):
        assert (root / directory).is_dir(), directory
    assert (root / "framework/workspace-formats.md").read_bytes() == (
        DOCS / "workspace-formats.md"
    ).read_bytes()
    assert (root / "CLAUDE.md").readlink() == Path("AGENTS.md")
    assert ".workspace-pending/" in (root / ".gitignore").read_text()
    assert not list(root.rglob("PROJECT.md"))
    assert not list(root.rglob("C-*.md"))
    # Local Git only, without commits.
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"], capture_output=True
    )
    assert head.returncode != 0


def test_init_output_names_root_scope_and_next_action(tmp_path):
    root = tmp_path / "lab"
    result = init(root)
    assert result.exit_code == 0, result.output
    assert f"Workspace: {root} | name: lab" in result.stdout
    assert "direction: none confirmed | projects: none | no model session started" in result.stdout
    assert f"Next: toulmin status --root {root}" in result.stdout
    assert 'name: "lab"' in (root / "WORKSPACE.md").read_text()


def test_status_reports_absent_direction_handoff_and_children(workspace):
    before = snapshot(workspace)
    result = status(workspace)
    assert result.exit_code == 0, result.output
    for line in (
        f"Root: {workspace}",
        "Scope: Workspace",
        "Workspace: Serving Research",
        "Direction: No confirmed direction yet",
        "Recorded next step: none",
        "Last handoff: none (no applied workspace handoff)",
        "Projects: none",
        "Proposals: none",
        "Resources: none",
        "Data: valid",
    ):
        assert line in result.stdout
    assert snapshot(workspace) == before  # read-only, including mtimes


def test_repeated_init_preserves_customized_files_and_writes_nothing(workspace):
    agents = workspace / "AGENTS.md"
    agents.write_text(agents.read_text() + "\nResearcher's own rule.\n")
    before = snapshot(workspace)
    result = init(workspace)
    assert result.exit_code == 0, result.output
    assert "Workspace already initialized" in result.stdout
    assert "name: Serving Research | nothing written" in result.stdout
    assert snapshot(workspace) == before


def test_repeated_init_does_not_rename_or_repair(workspace):
    before = snapshot(workspace)
    result = init(workspace, "--name", "Other")
    assert result.exit_code == 1
    assert "does not rename" in result.stderr
    charter = workspace / "WORKSPACE.md"
    charter.write_text(charter.read_text().replace("charter_revision: 0", "charter_revision: x"))
    before = snapshot(workspace)
    result = init(workspace)
    assert result.exit_code == 1
    assert "charter_revision" in result.stderr and "does not repair" in result.stderr
    assert snapshot(workspace) == before


def test_interrupted_setup_is_reported_then_completed_by_rerun(workspace):
    (workspace / "WORKSPACE.md").unlink()
    (workspace / "roles/scribe.md").unlink()
    before = snapshot(workspace)
    result = status(workspace)
    assert result.exit_code == 1
    assert "setup incomplete; rerun `toulmin init ROOT`" in result.stderr
    assert snapshot(workspace) == before
    result = init(workspace, "--name", "Serving Research")
    assert result.exit_code == 0, result.output
    assert "created entries: 2" in result.stdout
    assert digest((workspace / "WORKSPACE.md").read_bytes()) == CONTRACT_INITIAL_SHA256


def test_modified_template_in_incomplete_setup_is_refused_not_overwritten(workspace):
    (workspace / "WORKSPACE.md").unlink()
    (workspace / "AGENTS.md").write_text("Edited before setup finished.\n")
    before = snapshot(workspace)
    result = init(workspace)
    assert result.exit_code == 1
    assert "unexpected or modified: AGENTS.md" in result.stderr
    assert snapshot(workspace) == before


def test_unrelated_nonempty_root_is_refused_without_writes(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("Someone else's repository.\n")
    result = init(root)
    assert result.exit_code == 1
    assert "not empty and not a Toulmin workspace" in result.stderr
    assert "README.md" in result.stderr
    assert sorted(path.name for path in root.iterdir()) == ["README.md"]
    result = status(root)
    assert result.exit_code == 1
    assert "not a Toulmin workbench" in result.stderr


def test_existing_empty_git_repository_can_become_a_workspace(tmp_path):
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    result = init(root)
    assert result.exit_code == 0, result.output
    assert (root / "WORKSPACE.md").is_file()


def test_missing_root_status_does_not_create_it(tmp_path):
    root = tmp_path / "absent"
    result = status(root)
    assert result.exit_code == 1
    assert "does not exist" in result.stderr
    assert not root.exists()


def test_legacy_workbench_stays_valid_and_is_not_upgraded(tmp_path):
    root = tmp_path / "legacy"
    initialize(root, "demo")
    before = snapshot(root)
    result = status(root)
    assert result.exit_code == 0, result.output
    assert "Workspace state: not configured" in result.stdout
    assert "demo | stage=explore" in result.stdout
    assert "adoption arrives in a later release" in result.stdout
    result = init(root)
    assert result.exit_code == 1
    assert "init does not upgrade it" in result.stderr
    assert snapshot(root) == before
    assert status(root, "demo").exit_code == 0
    assert not (root / "WORKSPACE.md").exists()


def test_legacy_project_init_route_is_refused_on_workspace_root(workspace):
    before = snapshot(workspace)
    result = init(workspace, "--project", "scheduling")
    assert result.exit_code == 1
    assert "workspace root: init --project is refused" in result.stderr
    assert snapshot(workspace) == before


def test_name_option_is_workspace_only(tmp_path):
    result = init(tmp_path / "x", "--project", "demo", "--name", "X")
    assert result.exit_code == 2
    assert not (tmp_path / "x").exists()


def test_template_setup_in_tui_is_refused_on_workspace_root(workspace):
    before = snapshot(workspace)
    with pytest.raises(FormatError, match="workspace root"):
        WorkspaceService().create_project(workspace, "scheduling", "Goal.", "Motivation.")
    assert snapshot(workspace) == before


def test_omitted_project_selects_workspace_even_with_one_child(workspace):
    add_child(workspace)
    result = status(workspace)
    assert result.exit_code == 0, result.output
    assert "Scope: Workspace" in result.stdout
    assert "scheduling | stage=explore" in result.stdout
    project = status(workspace, "scheduling")
    assert project.exit_code == 0, project.output
    assert "Project: scheduling" in project.stdout
    conflict = status(workspace, "scheduling", "--workspace")
    assert conflict.exit_code == 2


def test_child_qualified_references_are_unchanged_in_workspace(workspace):
    add_child(workspace, "scheduling")
    other = add_child(workspace, "caching")
    brief = other / "brief.md"
    brief.write_text(brief.read_text() + "\nSee [[scheduling/C-001]].\n")
    assert status(workspace, "caching").exit_code == 1  # missing object, as before WI2
    assert "scheduling/C-001" in status(workspace, "caching").stderr


def test_status_from_project_directory_names_the_root(workspace, monkeypatch):
    child = add_child(workspace)
    monkeypatch.chdir(child)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert f"rerun with --root {workspace}" in result.stderr


@pytest.mark.parametrize(
    ("header", "body", "message"),
    [
        (
            [
                'name: "S"',
                "charter_revision: 0",
                "charter_receipt: runs/20261104T101500Z-proposal-"
                "a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md",
                "next_step: null",
                "last_handoff: null",
            ],
            "",
            "charter_receipt: must be null at revision 0",
        ),
        (
            ['name: "S"', "charter_revision: 0", "charter_receipt: null"]
            + ["next_step: null", "last_handoff: null"],
            "## Goal\nNot a workspace section.\n",
            "body.Goal: unknown workspace section",
        ),
        (
            ['name: "S"', "charter_revision: 0", "charter_receipt: null"]
            + ["next_step: null", "last_handoff: null"],
            "## Direction\n\n## Constraints\nOnly synthetic traces.\n",
            "body.Direction: required content empty",
        ),
        (
            ['name: "S"', "charter_revision: 0", "charter_receipt: null"]
            + ["next_step: null", "last_handoff: null"],
            "## Focus\nLater.\n\n## Direction\nFirst.\n",
            "sections must appear as Direction, Constraints, Focus",
        ),
        (
            ['name: "S"', "charter_revision: 0", "charter_receipt: null"]
            + ["next_step: null", "last_handoff: null"],
            "## Direction\nSee [[C-001]].\n",
            "unqualified reference in workspace scope",
        ),
        (
            ['name: "S"', "charter_revision: 0", "charter_receipt: null"]
            + ["next_step: null", "last_handoff: null", "stage: explore"],
            "",
            "stage: unknown field",
        ),
        (
            ['name: "S"', "charter_revision: 0", "charter_receipt: null"]
            + ["next_step: null", "last_handoff: null"],
            "line\n" * 40,
            "must fit within 40 lines",
        ),
    ],
)
def test_malformed_charter_is_reported_not_repaired(workspace, header, body, message):
    write_charter(workspace, header, body)
    before = snapshot(workspace)
    result = status(workspace)
    assert result.exit_code == 1
    assert message in result.stderr
    assert "Data: INVALID" in result.stdout
    assert snapshot(workspace) == before


def test_confirmed_sections_and_qualified_focus_reference(workspace):
    add_child(workspace)
    write_charter(
        workspace,
        ['name: "Serving Research"', "charter_revision: 0", "charter_receipt: null"]
        + ['next_step: "Propose the scheduling child."', "last_handoff: null"],
        "## Direction\nSingle-node tail latency.\n\n## Focus\nStart from [[scheduling/C-001]].\n",
    )
    result = status(workspace)
    assert result.exit_code == 1  # the child has no C-001 yet
    assert "[[scheduling/C-001]]" in result.stderr
    (workspace / "WORKSPACE.md").write_text(
        (workspace / "WORKSPACE.md").read_text().replace("[[scheduling/C-001]]", "scheduling")
    )
    result = status(workspace)
    assert result.exit_code == 0, result.output
    assert "Direction: Single-node tail latency." in result.stdout
    assert "Focus: Start from scheduling." in result.stdout
    assert "Recorded next step: Propose the scheduling child." in result.stdout


def test_missing_receipt_and_handoff_targets_are_errors(workspace):
    write_charter(
        workspace,
        [
            'name: "S"',
            "charter_revision: 1",
            "charter_receipt: runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b"
            "/receipt.md",
            "next_step: null",
            "last_handoff: 20261104T113500Z-" + "e" * 64 + ".md",
        ],
        "## Direction\nD.\n",
    )
    result = status(workspace)
    assert result.exit_code == 1
    assert "charter_receipt" in result.stderr and "last_handoff" in result.stderr


def test_symlinks_are_refused(workspace, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_bytes((workspace / "WORKSPACE.md").read_bytes())
    (workspace / "WORKSPACE.md").unlink()
    (workspace / "WORKSPACE.md").symlink_to(outside)
    result = status(workspace)
    assert result.exit_code == 1
    assert "symlinks forbidden" in result.stderr
    (workspace / "WORKSPACE.md").unlink()
    (workspace / "WORKSPACE.md").write_bytes(outside.read_bytes())
    (workspace / "projects/linked").symlink_to(tmp_path)
    result = status(workspace)
    assert result.exit_code == 1
    assert "projects/linked: expected a project directory" in result.stderr
    link = tmp_path / "alias"
    link.symlink_to(workspace)
    result = status(link)
    assert result.exit_code == 1
    assert "directory symlinks forbidden" in result.stderr


def packet(root, name, supersedes=None, tamper=False):
    folder = root / "runs" / name
    folder.mkdir()
    header = "---\nschema_version: 1\nkind: workspace-change\n"
    header += f"supersedes: {supersedes or 'null'}\n---\n## Question\nQ?\n"
    (folder / "packet.md").write_text(header)
    seal = hashlib.sha256(header.encode()).hexdigest()
    (folder / "seal").write_text(seal + "\n")
    if tamper:
        (folder / "packet.md").write_text(header + "edited\n")
    return f"runs/{name}", seal


def receipt(root, relative, seal, disposition):
    (root / relative / "receipt.md").write_text(
        "---\nschema_version: 1\nkind: workspace-receipt\n"
        f"record: {relative}/packet.md\nrecord_sha256: {seal}\n"
        f'disposition: {disposition}\nactor: R\nat: "2026-11-04T10:20:00Z"\n'
        "approval_text: null\n"
        + ("reason: null\n" if disposition == "applied" else 'reason: "Not now."\n')
        + "results: []\n---\nReceipt.\n"
    )


def test_proposal_dispositions_are_derived_from_files(workspace):
    stamp = "20261104T10{:02d}00Z-proposal-" + "0" * 31 + "{}"
    old, _ = packet(workspace, stamp.format(0, "1"))
    packet(workspace, stamp.format(1, "2"), supersedes=old)
    applied, seal = packet(workspace, stamp.format(2, "3"))
    receipt(workspace, applied, seal, "applied")
    rejected, seal = packet(workspace, stamp.format(3, "4"))
    receipt(workspace, rejected, seal, "rejected")
    result = status(workspace, "--verbose")
    assert result.exit_code == 0, result.output
    assert f"{old} | change | superseded" in result.stdout
    assert "proposal-00000000000000000000000000000002 | change | pending" in result.stdout
    assert f"{applied} | change | applied" in result.stdout
    assert f"{rejected} | change | rejected" in result.stdout
    brief = status(workspace)
    assert "3 applied, rejected or superseded; --verbose lists them" in brief.stdout
    assert f"{applied} |" not in brief.stdout


def test_tampered_packet_and_journal_make_data_invalid(workspace):
    stamp = "20261104T100000Z-proposal-" + "0" * 31
    tampered, _ = packet(workspace, stamp + "1", tamper=True)
    result = status(workspace)
    assert result.exit_code == 1
    assert f"{tampered} | change | invalid" in result.stdout
    assert "seal does not match packet.md" in result.stderr
    shutil.rmtree(workspace / tampered)
    pending, _ = packet(workspace, stamp + "2")
    journal = workspace / ".workspace-pending"
    journal.mkdir()
    (journal / "intent.md").write_text(
        "---\nschema_version: 1\noperation: workspace-change\n"
        f"record: {pending}/packet.md\n---\nIntent.\n"
    )
    result = status(workspace)
    assert result.exit_code == 1
    assert f"{pending} | change | incomplete" in result.stdout
    assert "incomplete workspace-change" in result.stderr


def test_misplaced_root_run_object_is_an_error(workspace):
    (workspace / "runs/R-001.md").write_text("---\nschema_version: 1\n---\n")
    result = status(workspace)
    assert result.exit_code == 1
    assert "misplaced Run object" in result.stderr


def test_invalid_resource_description_is_reported_not_repaired(workspace):
    path = workspace / "shared/resources/synthetic-queue-trace.md"
    path.write_text("---\n---\n")
    result = status(workspace)
    assert result.exit_code == 1
    assert "synthetic-queue-trace | invalid data" in result.stdout
    assert path.read_text() == "---\n---\n"
