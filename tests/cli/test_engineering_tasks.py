"""O4: engineering delegation without scientific objects; fake Chief, temporary repositories."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from toulmin.adapters.base import Finished
from toulmin.adapters.chief import ChiefClient
from toulmin.application import engineering_tasks as tasks
from toulmin.application.engineering_task_import import apply_task_import, prepare_task_import
from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.engineering_tasks import parse_task_import, render_task_import
from toulmin.protocols.engineering_tasks import task_inventory, write_task_draft


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def task_env(workbench, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "code"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "main.py").write_text("print('base')\n")
    git(repo, "add", "main.py")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Base",
    )
    base = git(repo, "rev-parse", "HEAD")
    home = tmp_path / "chief"
    home.mkdir()
    (workbench / "tools/chief.toml").write_text(
        f'command = "MUST_NOT_RUN_CHIEF"\nhome = {json.dumps(str(home))}\n'
    )
    draft = write_task_draft(workbench, "demo", repo=str(repo), name="engineering")
    doc = decode(draft.read_bytes(), str(draft))
    doc.header.update(
        {
            "checks": ["python main.py"],
            "protected": ["README.md"],
            "task_id": "demo-engineering",
            "command": "claude-mix",
        }
    )
    doc.body = "## Goal\nAdd a useful engineering helper.\n\n## Scope\nOnly main.py.\n"
    draft.write_bytes(encode(doc))
    relative = draft.relative_to(workbench).as_posix()
    launched = []

    def new(self, contract, task_id, base_branch, *, trust=False):
        launched.append(json.loads(contract.read_bytes()))
        task = home / "tasks" / task_id
        task.mkdir(parents=True)
        (task / "task.json").write_text(
            json.dumps(
                {
                    "repo": str(repo),
                    "base": base,
                    "branch": "main",
                    "state": "done",
                    "tool": "claude",
                    "session_id": "fake-worker",
                    "review": {"head": base, "verdict": "pass"},
                }
            )
        )
        (task / "review.md").write_text("Worker review fixture.\n")
        (home / "checks.json").write_text(
            json.dumps(
                {
                    "fake-worker": {
                        "results": [{"cmd": "python main.py", "code": 0, "tail": "base"}]
                    },
                    "unrelated-session": {"private": "must not be archived"},
                }
            )
        )
        return Finished(0, "Created fake task", "", 0)

    monkeypatch.setattr(ChiefClient, "new", new)
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    return SimpleNamespace(
        root=workbench,
        repo=repo,
        base=base,
        home=home,
        draft=draft,
        relative=relative,
        launched=launched,
    )


def submit(env):
    shown = tasks.prepare_task(env.root, "demo", env.relative)
    assert not shown.problems
    return tasks.apply_task(env.root, "demo", shown, "Researcher", "operator test approval")


def test_prepare_freezes_baseline_and_needs_no_claim_or_spec(task_env):
    env = task_env
    before = snapshot(env.root)
    shown = tasks.prepare_task(env.root, "demo", env.relative)
    assert not shown.problems
    assert shown.plan.contract["base_branch"] == env.base
    assert shown.plan.contract["command"] == "claude-mix"
    assert shown.plan.contract["protected"] == ["README.md"]
    assert snapshot(env.root) == before
    assert not list((env.root / "projects/demo/claims").glob("*.md"))


def test_decide_submits_and_repeat_is_idempotent(task_env):
    env = task_env
    result = CliRunner().invoke(
        app, ["decide", "--root", str(env.root), "--confirmed-by", "R"], input="a\n"
    )
    assert result.exit_code == 0, result.output
    assert "applied" in result.output
    assert len(env.launched) == 1
    assert task_inventory(env.root, "demo") == ((), ())
    shown = tasks.prepare_task(env.root, "demo", env.relative)
    assert tasks.apply_task(env.root, "demo", shown, "R", "repeat").disposition == "applied"
    assert len(env.launched) == 1
    assert tasks.engineering_task_ids(env.root, "demo") == ("demo-engineering",)


def test_dirty_repository_and_changed_preview_are_refused(task_env):
    env = task_env
    shown = tasks.prepare_task(env.root, "demo", env.relative)
    (env.repo / "untracked.txt").write_text("must not silently include this")
    assert "uncommitted changes" in tasks.prepare_task(env.root, "demo", env.relative).problems[0]
    with pytest.raises(FormatError, match="uncommitted changes"):
        tasks.apply_task(env.root, "demo", shown, "R", "approve")
    (env.repo / "untracked.txt").unlink()
    env.draft.write_text(env.draft.read_text().replace("Only main.py.", "Different scope."))
    with pytest.raises(FormatError, match="changed since preview"):
        tasks.apply_task(env.root, "demo", shown, "R", "approve")
    assert not env.launched


def test_task_collision_rejected(task_env):
    env = task_env
    directory = env.home / "tasks/demo-engineering"
    directory.mkdir(parents=True)
    (directory / "task.json").write_text(json.dumps({"repo": str(env.repo), "state": "done"}))
    assert "already taken" in tasks.prepare_task(env.root, "demo", env.relative).problems[0]
    assert not env.launched


def test_crash_after_launch_recovers_without_duplicate(task_env, monkeypatch):
    env = task_env
    original = tasks.finish_task
    monkeypatch.setattr(
        tasks, "finish_task", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("crash"))
    )
    with pytest.raises(RuntimeError, match="crash"):
        submit(env)
    monkeypatch.setattr(tasks, "finish_task", original)
    shown = tasks.prepare_task(env.root, "demo", env.relative)
    assert shown.interrupted and shown.recovered and not shown.problems
    tasks.apply_task(env.root, "demo", shown, "R", "recover")
    assert len(env.launched) == 1


def test_crash_while_freezing_contract_is_recoverable(task_env, monkeypatch):
    env = task_env
    original = tasks.write_atomic

    def crash(path, data, **kwargs):
        if path.name == "request.json":
            raise RuntimeError("freeze crash")
        return original(path, data, **kwargs)

    monkeypatch.setattr(tasks, "write_atomic", crash)
    with pytest.raises(RuntimeError, match="freeze crash"):
        submit(env)
    assert not env.launched
    assert not list((env.root / "projects/demo/runs").glob("*-task-*/contract.json"))
    monkeypatch.setattr(tasks, "write_atomic", original)
    shown = tasks.prepare_task(env.root, "demo", env.relative)
    assert shown.interrupted and not shown.problems
    tasks.apply_task(env.root, "demo", shown, "R", "recover")
    assert len(env.launched) == 1


def test_failed_launcher_reconciles_created_task(task_env, monkeypatch):
    env = task_env
    original = ChiefClient.new

    def new(self, *args, **kwargs):
        original(self, *args, **kwargs)
        return Finished(None, "", "timeout after create", 0)

    monkeypatch.setattr(ChiefClient, "new", new)
    assert submit(env).disposition == "applied"
    assert len(env.launched) == 1


def test_source_selection_uses_validated_mapping(task_env, monkeypatch):
    from toulmin.application import sources

    env = task_env
    doc = decode(env.draft.read_bytes(), str(env.draft))
    doc.header.update({"source": "source-a", "repo": None})
    env.draft.write_bytes(encode(doc))
    monkeypatch.setattr(
        sources, "resolve_source", lambda *a: SimpleNamespace(kind="git", path=env.repo)
    )
    assert not tasks.prepare_task(env.root, "demo", env.relative).problems
    monkeypatch.setattr(
        sources, "resolve_source", lambda *a: SimpleNamespace(kind="directory", path=env.repo)
    )
    assert "require a git source" in tasks.prepare_task(env.root, "demo", env.relative).problems[0]


def test_import_preview_is_readonly_and_creates_only_run(task_env):
    env = task_env
    submit(env)
    before = snapshot(env.root)
    preview = prepare_task_import(env.root, "demo", "demo-engineering")
    assert snapshot(env.root) == before
    done = apply_task_import(env.root, "demo", preview, "R")
    assert done.run == "R-001" and done.disposition == "applied"
    assert parse_task_import(render_task_import(done), "test") == done
    for directory in ("claims", "specs", "evidence", "decisions"):
        assert not list((env.root / f"projects/demo/{directory}").glob("*.md"))
    proposals = list((env.root / "projects/demo/runs/proposals").glob("*.md"))
    assert len(proposals) == 2  # the request and its outcome only
    assert "via claude-mix" in (env.root / "projects/demo/runs/R-001.md").read_text()
    cache = (env.root / preview.archive / "checks.json").read_text()
    assert "base" in cache and "unrelated-session" not in cache
    assert (
        apply_task_import(
            env.root, "demo", prepare_task_import(env.root, "demo", "demo-engineering"), "R"
        )
        == done
    )


def test_import_cli_requires_confirmation_and_handles_abandonment(task_env):
    env = task_env
    submit(env)
    path = env.home / "tasks/demo-engineering/task.json"
    raw = json.loads(path.read_bytes())
    raw["state"] = "abandoned"
    path.write_text(json.dumps(raw))
    args = ["task", "import", "demo", "demo-engineering", "--root", str(env.root)]
    runner = CliRunner()
    before = snapshot(env.root)
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Preview only" in result.output and snapshot(env.root) == before
    result = runner.invoke(app, args + ["--confirm", "--confirmed-by", "R"])
    assert result.exit_code == 0, result.output
    assert "status: failed" in (env.root / "projects/demo/runs/R-001.md").read_text()


def test_changed_import_inputs_and_artifact_tampering_are_refused(task_env):
    env = task_env
    submit(env)
    shown = prepare_task_import(env.root, "demo", "demo-engineering")
    (env.home / "tasks/demo-engineering/review.md").write_text("Changed worker review\n")
    with pytest.raises(FormatError, match="changed since preview"):
        apply_task_import(env.root, "demo", shown, "R")
    shown = prepare_task_import(env.root, "demo", "demo-engineering")
    done = apply_task_import(env.root, "demo", shown, "R")
    assert done.run == "R-001"
    (env.root / shown.archive / "review.md").write_text("Tampered")
    with pytest.raises(FormatError, match="artifact changed"):
        prepare_task_import(env.root, "demo", "demo-engineering")


def test_import_recovers_run_published_before_receipt(task_env, monkeypatch):
    from toulmin.protocols import engineering_task_import as protocol

    env = task_env
    submit(env)
    shown = prepare_task_import(env.root, "demo", "demo-engineering")
    original = protocol.write_atomic

    def crash(path, data, **kwargs):
        if path.name == "import.json" and kwargs.get("replace"):
            raise RuntimeError("receipt crash")
        return original(path, data, **kwargs)

    monkeypatch.setattr(protocol, "write_atomic", crash)
    with pytest.raises(RuntimeError, match="receipt crash"):
        apply_task_import(env.root, "demo", shown, "R")
    monkeypatch.setattr(protocol, "write_atomic", original)
    assert (
        apply_task_import(
            env.root, "demo", prepare_task_import(env.root, "demo", "demo-engineering"), "R"
        ).run
        == "R-001"
    )
    assert len(list((env.root / "projects/demo/runs").glob("R-*.md"))) == 1


def test_unfinished_engineering_task_blocks_workspace_removal(task_env):
    from toulmin.application.workspace_remove import _chief_tasks

    env = task_env
    submit(env)
    path = env.home / "tasks/demo-engineering/task.json"
    raw = json.loads(path.read_bytes())
    raw["state"] = "running"
    path.write_text(json.dumps(raw))
    found, blockers = _chief_tasks(env.root, ("demo",))
    assert any(item.id == "demo-engineering" for item in found)
    assert any("demo-engineering is running" in item for item in blockers)
    with pytest.raises(FormatError, match="needs done or abandoned"):
        prepare_task_import(env.root, "demo", "demo-engineering")


def test_import_refuses_changed_frozen_contract_and_run(task_env):
    env = task_env
    submit(env)
    shown = prepare_task_import(env.root, "demo", "demo-engineering")
    contract_path = env.root / shown.archive.removesuffix("-result") / "contract.json"
    original = contract_path.read_bytes()
    contract_path.write_bytes(original + b"\n")
    with pytest.raises(FormatError, match="submission differs"):
        prepare_task_import(env.root, "demo", "demo-engineering")
    contract_path.write_bytes(original)
    apply_task_import(env.root, "demo", shown, "R")
    run = env.root / "projects/demo/runs/R-001.md"
    run.write_text(run.read_text().replace("Imported engineering task", "Changed engineering task"))
    with pytest.raises(FormatError, match="does not match its Run"):
        prepare_task_import(env.root, "demo", "demo-engineering")


@pytest.mark.parametrize(
    "field,value",
    [
        ("baseline", "--bad"),
        ("checks", []),
        ("protected", ["../escape"]),
        ("budget", {"rounds": 0, "hours": 1}),
        ("command", "/bin/sh"),
    ],
)
def test_invalid_requests_do_not_launch(task_env, field, value):
    env = task_env
    doc = decode(env.draft.read_bytes(), str(env.draft))
    doc.header[field] = value
    env.draft.write_bytes(encode(doc))
    with pytest.raises(FormatError):
        tasks.prepare_task(env.root, "demo", env.relative)
    assert not env.launched
