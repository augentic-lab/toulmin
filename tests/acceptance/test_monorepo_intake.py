"""Focused monorepo intake preserves reviewed policy across later workflows.

Temporary repositories and fake native sessions only; no source scripts, subscribed
providers or Chief workers run. These checks do not establish usability acceptance.
"""

import json

import pytest

from tests.acceptance.wo_support import (
    OVERVIEW,
    catalog,
    child_input,
    disposition,
    git,
    invoke,
    propose,
    repository,
    sha,
    tree,
)
from toulmin.application.aoe import AoEWorkspace
from toulmin.application.scoped_tasks import prepare
from toulmin.application.sources import scope_source_reports
from toulmin.core.codec import decode, encode
from toulmin.core.scope import Scope

FOCUS = "DefenceTools/symbolic_executor"
POLICY = {
    "include": [FOCUS, "README.md"],
    "exclude": [f"{FOCUS}/generated", f"{FOCUS}/notes.md"],
}
SELECTED = [f"{FOCUS}/executor.py", "README.md"]


@pytest.fixture
def monorepo(wo):
    files = {
        f"{FOCUS}/executor.py": "def execute():\n    return 'bounded fixture'\n",
        f"{FOCUS}/generated/skip.py": "GENERATED = True\n",
        f"{FOCUS}/notes.md": "Excluded implementation notes.\n",
        "README.md": "# Fixture monorepo\nOne selected subsystem.\n",
        "unrelated/other.py": "UNRELATED = True\n",
    }
    for name, text in files.items():
        path = wo.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(wo.source, "add", ".")
    git(
        wo.source,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "Fixture monorepo layout",
    )
    return wo


def policy_flags():
    return [
        *(arg for path in POLICY["include"] for arg in ("--include", path)),
        *(arg for path in POLICY["exclude"] for arg in ("--exclude", path)),
    ]


def focused_a(wo):
    return propose(
        wo.root,
        "onboard",
        wo.source,
        "--init",
        "--register-source",
        "source-main",
        *policy_flags(),
    )


def observed(packet):
    return json.loads((packet / "inventory/source-main.json").read_bytes())


def assert_focused(observation):
    assert [item["path"] for item in observation["files"]] == SELECTED
    assert json.dumps(POLICY, ensure_ascii=True, sort_keys=True) in observation["coverage"]
    assert not observation["truncated"]


def test_focused_a_preserves_root_identity_and_ordered_policy_without_children(monorepo):
    wo = monorepo
    before = tree(wo.source)
    head = git(wo.source, "rev-parse", "HEAD")
    root_identity = "git:" + sha(git(wo.source, "rev-list", "--max-parents=0", "HEAD").encode())
    packet = focused_a(wo)
    observation = observed(packet)
    assert_focused(observation)
    assert observation["identity"] == root_identity and observation["head"] == head
    assert not (wo.root / "sources.toml").exists()
    assert not [path for path in (wo.root / "projects").iterdir() if path.is_dir()]
    disposition(wo.root, packet)
    definition = catalog(wo.root)["definitions"][0]
    assert definition["inspection"] == POLICY
    assert definition["definition_revision"] == 2 and definition["identity"] == root_identity
    assert not [path for path in (wo.root / "projects").iterdir() if path.is_dir()]
    local = (wo.root / "tools/sources.local.toml").read_text()
    assert str(wo.source) in local and str(wo.source / FOCUS) not in local
    assert any(
        "matches bounded confirmed snapshot" in line for line in scope_source_reports(wo.root, None)
    )
    assert tree(wo.source) == before


def test_c_and_overview_inherit_registered_policy_without_flags(monorepo):
    wo = monorepo
    first = focused_a(wo)
    disposition(wo.root, first)
    definition = catalog(wo.root)["definitions"][0]
    overview_before = (wo.root / "overview.md").read_bytes()
    packet = propose(
        wo.root,
        "onboard",
        wo.source,
        "--source-id",
        "source-main",
        "--project",
        "analysis",
        "--project-input",
        child_input(wo.root, "analysis"),
    )
    assert_focused(observed(packet))
    disposition(wo.root, packet)
    assert (wo.root / "projects/analysis/PROJECT.md").exists()
    assert catalog(wo.root)["definitions"] == [definition]
    assert (wo.root / "overview.md").read_bytes() == overview_before
    input_path = wo.tmp / "overview-input.md"
    input_path.write_text(OVERVIEW)
    update = propose(
        wo.root,
        "overview",
        "--workspace",
        "--source",
        "source-main",
        "--input",
        input_path,
        "--rationale",
        "Record a bounded subsystem reading",
    )
    assert_focused(observed(update))
    disposition(wo.root, update)
    header = decode((wo.root / "overview.md").read_bytes(), "overview").header
    assert header["revision"] == 2
    snapshot = wo.root / header["sources"][0]["snapshot"]
    assert_focused(json.loads(snapshot.read_bytes()))


def test_explicit_policy_mismatch_cannot_change_registered_selection(monorepo):
    wo = monorepo
    packet = focused_a(wo)
    disposition(wo.root, packet)
    project_input = child_input(wo.root, "analysis")
    before = tree(wo.root)
    result = invoke(
        "onboard",
        wo.source,
        "--source-id",
        "source-main",
        "--project",
        "analysis",
        "--project-input",
        project_input,
        "--include",
        "README.md",
        "--root",
        wo.root,
        code=1,
    )
    assert "differs" in result.output and "registered" in result.output
    assert tree(wo.root) == before


def test_focused_work_at_refuses_before_initializing_records(monorepo):
    wo = monorepo
    target = repository(wo.tmp / "target")
    before = tree(wo.source)
    result = invoke(
        "onboard",
        wo.source,
        "--init",
        "--work-at",
        target,
        *policy_flags(),
        "--root",
        wo.root,
        code=1,
    )
    assert "--work-at" in result.output
    assert not wo.root.exists() and tree(wo.source) == before


@pytest.mark.parametrize("selection", ["../escape", ".", "missing", "symlink", "symlink/file.py"])
def test_invalid_or_unsafe_selection_refuses_before_initializing_records(monorepo, selection):
    wo = monorepo
    (wo.source / "symlink").symlink_to(wo.source / FOCUS, target_is_directory=True)
    before = tree(wo.source)
    invoke(
        "onboard",
        wo.source,
        "--init",
        "--include",
        selection,
        "--root",
        wo.root,
        code=1,
    )
    assert not wo.root.exists() and tree(wo.source) == before


@pytest.mark.parametrize("selection", ["missing", "symlink"])
def test_bad_exclusion_is_validated_before_initializing_records(monorepo, selection):
    wo = monorepo
    (wo.source / "symlink").symlink_to(wo.source / FOCUS, target_is_directory=True)
    invoke(
        "onboard",
        wo.source,
        "--init",
        "--include",
        FOCUS,
        "--exclude",
        selection,
        "--root",
        wo.root,
        code=1,
    )
    assert not wo.root.exists()


def test_exclude_alone_refuses_before_initializing_records(monorepo):
    wo = monorepo
    invoke(
        "onboard",
        wo.source,
        "--init",
        "--exclude",
        FOCUS,
        "--root",
        wo.root,
        code=1,
    )
    assert not wo.root.exists()


def test_selected_content_change_blocks_apply_without_publishing_formal_state(monorepo):
    wo = monorepo
    selected = wo.source / FOCUS / "executor.py"
    selected.write_text("def execute():\n    return 'original'\n")
    packet = focused_a(wo)
    prior = observed(packet)
    selected.write_text("def execute():\n    return 'changed!'\n")
    assert prior["status"] == git(wo.source, "status", "--porcelain=v1", "--untracked-files=no")
    before = tree(wo.root)
    result = disposition(wo.root, packet, code=1)
    assert "changed since preview" in result.output
    assert tree(wo.root) == before
    assert not (wo.root / "sources.toml").exists()


def test_whole_repository_dirty_status_is_visible_outside_selected_files(monorepo):
    wo = monorepo
    (wo.source / "unrelated/other.py").write_text("UNRELATED = False\n")
    packet = focused_a(wo)
    observation = observed(packet)
    assert_focused(observation)
    assert "unrelated/other.py" in observation["status"]


def test_native_v4_keeps_git_root_and_focused_observation_in_fingerprint(monorepo, native):
    wo = monorepo
    packet = focused_a(wo)
    disposition(wo.root, packet)
    service = AoEWorkspace(wo.root, None, native)
    view = service.open(codex_sandbox="inherit")
    assert view.binding.cwd == str(wo.source)
    assert native.created[0][0] == wo.source
    service.acknowledge(view.binding.token)
    assert service.status(check_session=False).context_status == "acknowledged"
    (wo.source / FOCUS / "executor.py").write_text("def execute():\n    return 'new observation'\n")
    assert "stale" in service.status(check_session=False).context_status


def test_task_snapshot_and_preview_retain_policy_and_global_cleanliness(monorepo):
    wo = monorepo
    packet = focused_a(wo)
    disposition(wo.root, packet)
    home = wo.tmp / "fake-chief-home"
    home.mkdir()
    (wo.root / "tools/chief.local.toml").write_text(
        f'command = "MUST_NOT_EXECUTE_CHIEF"\nhome = {json.dumps(str(home))}\n'
    )
    invoke("draft", "task", "--workspace", "--source", "source-main", "--root", wo.root)
    request = next((wo.root / "runs/proposals").glob("task-*.md"))
    document = decode(request.read_bytes(), str(request))
    pin = document.header["source_pin"]
    assert_focused(json.loads((wo.root / pin["snapshot"]).read_bytes()))
    document.header["checks"] = ["python -m unittest"]
    document.body = (
        "## Goal\nImprove the selected fixture executor.\n\n"
        f"## Scope\nOnly {FOCUS}/executor.py; no other subsystem changes.\n"
    )
    request.write_bytes(encode(document))
    prepared = prepare(wo.root, Scope(), str(request))
    assert prepared.contract["repo"] == str(wo.source)
    assert prepared.request.pin == pin
    assert not list(home.iterdir())
    (wo.source / "unrelated/other.py").write_text("UNRELATED = False\n")
    result = invoke("task", "preview", "--workspace", request, "--root", wo.root, code=1)
    assert "uncommitted changes" in result.output
    assert not list(home.iterdir())
