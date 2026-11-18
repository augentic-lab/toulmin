"""R6: actual Git lineage and fake Chief state across normal test approval.

Model Chief.approve_tests' documented phase/base/protected update; never execute
Chief, native models or acceptance checks. All repositories/state are disposable.
"""

import json
from types import SimpleNamespace

import pytest

from tests.acceptance.wo_support import ACTOR, canonical, git, invoke, tree, v2_workspace
from tests.cli import test_engineering_tasks as legacy
from toulmin.adapters.base import Finished
from toulmin.adapters.chief import ChiefClient
from toulmin.application import scoped_task_import, scoped_tasks
from toulmin.application.engineering_task_import import apply_task_import, prepare_task_import
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.scope import Scope

legacy_env = legacy.task_env


def commit(repo, message):
    git(repo, "add", ".")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return git(repo, "rev-parse", "HEAD")


def approved_build(repo, baseline, task, worker):
    """Use a real separate worktree so source HEAD remains the frozen baseline."""
    branch = "chief/fixture-lifecycle"
    git(repo, "worktree", "add", "-qb", branch, str(worker), baseline)
    (worker / "tests").mkdir()
    (worker / "tests/test_helper.py").write_text(
        "import unittest\nfrom main import helper\n"
        "class HelperTest(unittest.TestCase):\n"
        "    def test_value(self):\n        self.assertEqual(helper(), 42)\n"
    )
    accepted = commit(worker, "Approved acceptance tests fixture")
    # The normal non-adopted Chief transition preserves immutable base_branch,
    # moves base to accepted tests, and extends rather than replaces protected.
    task.update(phase="build", base=accepted, worktree=str(worker), branch=branch)
    task["protected"] = list(dict.fromkeys([*task["protected"], "tests/test_helper.py"]))
    (worker / "main.py").write_text("def helper():\n    return 42\n")
    implemented = commit(worker, "Implement bounded helper fixture")
    task["review"] = {"head": implemented, "verdict": None}
    assert git(repo, "rev-parse", "HEAD") == baseline
    return accepted, implemented


@pytest.fixture(params=[None, "latency"], ids=["workspace-v2", "project-v2"])
def lifecycle(wo, monkeypatch, request):
    scope = Scope(request.param)
    v2_workspace(wo.root, wo.source, children=(scope.project,) if scope.project else ())
    home = wo.tmp / "fake-chief-home"
    home.mkdir()
    (wo.root / "tools/chief.local.toml").write_text(
        f'command = "NEVER_RUN_CHIEF"\nhome = {json.dumps(str(home))}\n'
    )
    selection = (scope.project,) if scope.project else ("--workspace",)
    invoke("draft", "task", *selection, "--root", wo.root, "--source", "source-main")
    (path,) = (wo.root / scope.records("runs") / "proposals").glob("task-*.md")
    document = decode(path.read_bytes(), str(path))
    document.header.update(checks=["python -m unittest discover -s tests"], protected=["AGENTS.md"])
    document.body = "## Goal\nImplement a bounded helper.\n\n## Scope\nOnly main.py and tests.\n"
    path.write_bytes(encode(document))
    launches = []

    def new(client, contract_path, task_id, base_branch, *, trust=False):
        contract = json.loads(contract_path.read_bytes())
        launches.append(contract)
        directory = home / "tasks" / task_id
        directory.mkdir(parents=True)
        task = {
            **contract,
            "id": task_id,
            "base": base_branch,
            "phase": "test",
            "state": "running",
            "session_id": "0123456789abcdef",
        }
        (directory / "task.json").write_bytes(canonical(task))
        return Finished(0, "Fake Chief task created", "", 0)

    monkeypatch.setattr(ChiefClient, "new", new)
    shown = scoped_tasks.prepare(wo.root, scope, str(path))
    scoped_tasks.apply(wo.root, scope, shown, ACTOR, "Fixture operator approval")
    task_path = home / "tasks" / shown.task_id / "task.json"
    task = json.loads(task_path.read_bytes())
    baseline = shown.contract["base_branch"]
    accepted, head = approved_build(wo.source, baseline, task, wo.tmp / "fake-worker")
    task_path.write_bytes(canonical(task))
    return SimpleNamespace(
        root=wo.root,
        source=wo.source,
        scope=scope,
        path=path,
        task=task,
        task_path=task_path,
        baseline=baseline,
        accepted=accepted,
        head=head,
        contract=shown.contract,
        launches=launches,
        selection=selection,
        tmp=wo.tmp,
    )


@pytest.mark.parametrize("state", ["done", "abandoned"])
def test_approved_tests_build_import_and_replay_keep_original_source_lineage(lifecycle, state):
    env = lifecycle
    env.task["state"] = state
    env.task_path.write_bytes(canonical(env.task))
    before = tree(env.root)
    source_before = tree(env.source)
    # Reconciliation must compare immutable contract fields, not Chief's current
    # scope base/protected additions, and must never start a second worker.
    reconciled = scoped_tasks.prepare(env.root, env.scope, str(env.path))
    assert reconciled.recovered and reconciled.contract == env.contract
    shown = scoped_task_import.prepare(env.root, env.scope, str(env.path))
    assert tree(env.root) == before and tree(env.source) == source_before
    assert shown.record.head == env.head
    assert shown.record.source_pin["head"] == env.baseline
    assert json.loads(shown.files["contract.json"])["base_branch"] == env.baseline
    assert env.accepted[:7] in shown.files["commits.txt"].decode()
    assert env.head[:7] in shown.files["commits.txt"].decode()
    assert b"tests/test_helper.py" in shown.files["diffstat.txt"]
    assert json.loads(shown.files["task.md"].split(b"\n", 1)[1])["base"] == env.accepted
    done = scoped_task_import.apply(env.root, env.scope, str(env.path), shown, ACTOR)
    assert done.disposition == "applied"
    if env.scope.project is None:
        assert done.run.endswith("/run.md")
        assert not list((env.root / "runs").glob("R-*.md"))
    else:
        assert done.run == "R-001"
    after = tree(env.root)
    # Replay consumes its sealed import; no continuing dependency on mutable Chief state.
    env.task_path.unlink()
    saved = scoped_task_import.prepare(env.root, env.scope, str(env.path))
    assert saved.existing
    assert scoped_task_import.apply(env.root, env.scope, str(env.path), saved, "Replay") == done
    assert tree(env.root) == after and len(env.launches) == 1


@pytest.mark.parametrize("state", ["running", "needs-you", "reviewing"])
def test_valid_approved_test_lineage_still_requires_terminal_chief_state(lifecycle, state):
    env = lifecycle
    env.task["state"] = state
    env.task_path.write_bytes(canonical(env.task))
    before = tree(env.root)
    result = invoke("task", "import", *env.selection, env.path, "--root", env.root, code=1)
    assert "requires done or abandoned" in result.output, result.output
    assert "differs from frozen contract" not in result.output
    assert tree(env.root) == before and len(env.launches) == 1


@pytest.mark.parametrize(
    "damage",
    [
        "conflicting-base-branch",
        "missing-base-branch",
        "missing-base",
        "unknown-base",
        "ambiguous-base",
        "unrelated-base",
        "wrong-phase",
        "changed-checks",
        "missing-checks",
        "changed-goal",
        "changed-repo",
        "weakened-protected",
        "malformed-protected",
        "missing-test-first",
        "changed-test-first",
        "unrelated-result",
    ],
)
def test_approved_test_transition_never_weakens_frozen_authority(lifecycle, damage):
    env = lifecycle
    task = env.task
    task["state"] = "done"
    if damage == "conflicting-base-branch":
        task["base_branch"] = env.accepted
    elif damage in {"missing-base-branch", "missing-base", "missing-checks", "missing-test-first"}:
        task.pop(damage.removeprefix("missing-").replace("-", "_"))
    elif damage == "unknown-base":
        task["base"] = "f" * 40
    elif damage == "ambiguous-base":
        task["base"] = "HEAD"
    elif damage in {"unrelated-base", "unrelated-result"}:
        tree_id = git(env.source, "rev-parse", f"{env.baseline}^{{tree}}")
        orphan = git(
            env.source,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree_id,
            "-m",
            "Unrelated lineage fixture",
        )
        if damage == "unrelated-base":
            task["base"] = orphan
        else:
            task["review"]["head"] = orphan
    elif damage == "wrong-phase":
        task["phase"] = "test"
    elif damage == "changed-checks":
        task["checks"] = ["true"]
    elif damage == "changed-goal":
        task["goal"] = "Different unapproved goal"
    elif damage == "changed-repo":
        task["repo"] = str(env.tmp)
    elif damage == "weakened-protected":
        task["protected"] = ["tests/test_helper.py"]
    elif damage == "malformed-protected":
        task["protected"] = [["AGENTS.md"]]
    else:
        task["test_first"] = False
    env.task_path.write_bytes(canonical(task))
    before = tree(env.root)
    with pytest.raises(FormatError):
        scoped_task_import.prepare(env.root, env.scope, str(env.path))
    assert tree(env.root) == before and len(env.launches) == 1


def test_old_sparse_chief_record_with_unchanged_base_remains_compatible(lifecycle):
    env = lifecycle
    task = {
        "repo": str(env.source),
        "base": env.baseline,
        "state": "done",
        "branch": env.task["branch"],
        "review": env.task["review"],
        "tool": "codex",
    }
    env.task_path.write_bytes(canonical(task))
    assert scoped_task_import.prepare(env.root, env.scope, str(env.path)).record.head == env.head


@pytest.mark.parametrize("state", ["done", "abandoned"])
def test_legacy_project_import_accepts_normal_chief_test_approval_without_migration(
    legacy_env, state
):
    env = legacy_env
    legacy.submit(env)
    task_path = env.home / "tasks/demo-engineering/task.json"
    task = {**json.loads(task_path.read_bytes()), **env.launched[0], "phase": "test"}
    accepted, head = approved_build(env.repo, env.base, task, env.repo.parent / "legacy-worker")
    task["state"] = state
    task_path.write_bytes(canonical(task))
    before = tree(env.root)
    shown = prepare_task_import(env.root, "demo", "demo-engineering")
    assert tree(env.root) == before
    assert shown.record.head == head
    assert json.loads(shown.files["contract.json"])["base_branch"] == env.base
    assert accepted[:7] in shown.files["commits.txt"].decode()
    done = apply_task_import(env.root, "demo", shown, ACTOR)
    assert done.run == "R-001"
    after = tree(env.root)
    assert (
        apply_task_import(
            env.root, "demo", prepare_task_import(env.root, "demo", "demo-engineering"), ACTOR
        )
        == done
    )
    assert tree(env.root) == after and len(env.launched) == 1
