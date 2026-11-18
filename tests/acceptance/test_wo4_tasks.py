"""WO4 scoped engineering export/result acceptance with a fake Chief adapter only."""

import json
import tomllib

import pytest

from tests.acceptance.wo_support import (
    ACTOR,
    WS,
    canonical,
    definition_sha,
    git,
    invoke,
    sha,
    tree,
    v2_workspace,
)
from toulmin.adapters.base import Finished
from toulmin.adapters.chief import ChiefClient
from toulmin.cli import decide
from toulmin.core.codec import decode, encode


@pytest.fixture
def task(wo, monkeypatch):
    definition = v2_workspace(wo.root, wo.source)
    home = wo.tmp / "fake-chief-home"
    home.mkdir()
    (wo.root / "tools/chief.local.toml").write_text(
        f'command = "MUST_NOT_EXECUTE_CHIEF"\nhome = {json.dumps(str(home))}\n'
    )
    invoke(
        "draft",
        "task",
        "--workspace",
        "--source",
        "source-main",
        "--root",
        wo.root,
        "--name",
        "bounded-helper",
    )
    proposals = list((wo.root / "runs/proposals").glob("task-*.md"))
    assert len(proposals) == 1
    request = proposals[0]
    document = decode(request.read_bytes(), str(request))
    assert document.header["schema_version"] == 2 and document.header["scope"] == WS
    assert "repo" not in document.header
    pin = document.header["source_pin"]
    assert pin["source"] == "source-main" and pin["definition_sha256"] == definition_sha(definition)
    assert pin["catalog_sha256"] == sha((wo.root / "sources.toml").read_bytes())
    assert pin["snapshot_sha256"] == sha((wo.root / pin["snapshot"]).read_bytes())
    assert pin["head"] == git(wo.source, "rev-parse", "HEAD")
    document.header.update(
        {
            "checks": ["python -m unittest"],
            "protected": ["AGENTS.md"],
            "tool": "claude",
            "command": "claude-mix",
            "trust": False,
        }
    )
    document.body = (
        "## Goal\nAdd a bounded parsing helper.\n\n## Scope\nOnly main.py; no research rulings.\n"
    )
    request.write_bytes(encode(document))
    wo.request = request
    wo.home = home
    wo.launched = []
    wo.uncertain = False

    def new(client, contract_path, task_id, base_branch, *, trust=False):
        assert not trust
        markers = list((wo.root / "runs/proposals").glob("*.outcome.md"))
        assert len(markers) == 1
        assert decode(markers[0].read_bytes(), "outcome").header["disposition"] == "applying"
        local = wo.root / f"tools/task-{sha(request.read_bytes())}.local.toml"
        assert local.exists(), "Freeze local export before any external side effect"
        intent = tomllib.loads(local.read_text())
        contract_raw = contract_path.read_bytes()
        assert intent["contract_json"].encode() == contract_raw
        frozen = json.loads(contract_raw)
        wo.launched.append((task_id, frozen))
        directory = home / "tasks" / task_id
        directory.mkdir(parents=True)
        (directory / "task.json").write_bytes(
            canonical(
                {
                    "repo": str(wo.source),
                    "base": base_branch,
                    "branch": "main",
                    "state": "done",
                    "tool": "claude",
                    "session_id": "fake-worker",
                    "review": {
                        "head": base_branch,
                        "verdict": "pass",
                        "summary": "Fake technical result; not researcher acceptance",
                    },
                }
            )
        )
        (directory / "review.md").write_text("Fake worker review; no real worker ran.\n")
        return Finished(None if wo.uncertain else 0, "", "lost response" if wo.uncertain else "", 0)

    monkeypatch.setattr(ChiefClient, "new", new)
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    return wo


def approve(task):
    return invoke(
        "decide",
        "--workspace",
        "--root",
        task.root,
        "--confirmed-by",
        ACTOR,
        "--no-notify",
        input="a\n",
    )


def test_workspace_task_preview_is_readonly_then_exports_exact_pinned_contract_without_objects(
    task,
):
    before = tree(task.root)
    preview = invoke("task", "preview", "--workspace", task.request, "--root", task.root)
    assert "source-main" in preview.output and "main.py" in preview.output
    assert tree(task.root) == before and not task.launched
    approve(task)
    assert len(task.launched) == 1
    task_id, contract = task.launched[0]
    assert task_id == "workspace-" + task.request.stem
    assert set(contract) == {
        "repo",
        "name",
        "goal",
        "base_branch",
        "checks",
        "protected",
        "budget",
        "tool",
        "test_first",
        "command",
    }
    assert contract["repo"] == str(task.source)
    assert contract["base_branch"] == git(task.source, "rev-parse", "HEAD")
    assert contract["checks"] == ["python -m unittest"] and contract["protected"] == ["AGENTS.md"]
    assert contract["command"] == "claude-mix" and "source-main" in contract["goal"]
    submissions = list((task.root / "runs").glob("*-task-*/submission.json"))
    assert len(submissions) == 1
    submission = json.loads(submissions[0].read_bytes())
    assert set(submission) == {
        "schema_version",
        "kind",
        "scope",
        "proposal",
        "proposal_sha256",
        "source_pin",
        "baseline",
        "task_id",
        "contract_sha256",
        "local_intent_sha256",
    }
    assert submission["schema_version"] == 2 and submission["scope"] == WS
    local = task.root / f"tools/task-{sha(task.request.read_bytes())}.local.toml"
    assert submission["local_intent_sha256"] == sha(local.read_bytes())
    assert submission["contract_sha256"] == sha(canonical(contract))
    assert [p for p in (task.root / "projects").iterdir() if p.is_dir()] == []
    for path in (task.root / "runs").rglob("*"):
        if path.is_file():
            assert str(task.source).encode() not in path.read_bytes(), path
            assert str(task.home).encode() not in path.read_bytes(), path


@pytest.mark.parametrize("change", ["dirty", "head", "pin", "scope", "absolute-repo", "checks"])
def test_invalid_or_stale_workspace_task_never_launches(task, change):
    if change == "dirty":
        (task.source / "main.py").write_text("print('dirty')\n")
    elif change == "head":
        git(
            task.source,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "Different baseline",
        )
    else:
        doc = decode(task.request.read_bytes(), "request")
        if change == "pin":
            doc.header["source_pin"]["definition_sha256"] = "a" * 64
        elif change == "scope":
            doc.header["scope"] = {"kind": "project", "project": "nonexistent"}
        elif change == "absolute-repo":
            doc.header["repo"] = str(task.source)
        elif change == "checks":
            doc.header["checks"] = []
        task.request.write_bytes(encode(doc))
    before = tree(task.root)
    invoke("task", "preview", "--workspace", task.request, "--root", task.root, code=1)
    assert not task.launched and tree(task.root) == before


def test_uncertain_chief_creation_reconciles_same_id_and_no_second_new(task):
    task.uncertain = True
    approve(task)
    assert len(task.launched) == 1
    invoke(
        "decide",
        "--workspace",
        "--root",
        task.root,
        "--confirmed-by",
        ACTOR,
        "--no-notify",
        input="a\n",
    )
    assert len(task.launched) == 1
    markers = list((task.root / "runs/proposals").glob("*.outcome.md"))
    assert decode(markers[0].read_bytes(), "outcome").header["disposition"] == "applied"


@pytest.mark.parametrize("state", ["done", "abandoned"])
def test_workspace_import_is_operational_run_with_exact_private_artifacts_and_idempotent_replay(
    task, state
):
    approve(task)
    task_id = task.launched[0][0]
    path = task.home / "tasks" / task_id / "task.json"
    value = json.loads(path.read_bytes())
    value["state"] = state
    path.write_bytes(canonical(value))
    args = ("task", "import", "--workspace", task.request, "--root", task.root)
    before = tree(task.root)
    invoke(*args)
    assert tree(task.root) == before
    invoke(*args, "--confirm", "--confirmed-by", ACTOR)
    records = list((task.root / "runs").glob("*-task-*-result/run.md"))
    assert len(records) == 1 and not list((task.root / "runs").glob("R-*.md"))
    doc = decode(records[0].read_bytes(), "operational run")
    assert set(doc.header) == {
        "schema_version",
        "kind",
        "scope",
        "created",
        "status",
        "source",
        "role",
        "model",
        "session_id",
        "duration_seconds",
        "input_files",
        "output",
    }
    assert doc.header["kind"] == "engineering-run" and doc.header["scope"] == WS
    assert doc.header["status"] == ("completed" if state == "done" else "failed")
    assert doc.header["source"] == {"kind": "human", "actor": ACTOR}
    assert doc.header["model"] is None, "Tool/command are not reported model identity"
    assert "## Summary" in doc.body
    if state == "abandoned":
        assert "## Failure" in doc.body
    imported = json.loads(records[0].with_name("import.json").read_bytes())
    assert set(imported) == {
        "schema_version",
        "kind",
        "task_id",
        "request",
        "request_sha256",
        "actor",
        "at",
        "state",
        "head",
        "tool",
        "command",
        "session_id",
        "files",
        "disposition",
        "run",
        "scope",
        "source_pin",
        "submission_sha256",
    }
    assert imported["schema_version"] == 2 and imported["scope"] == WS
    assert imported["run"] == records[0].relative_to(task.root).as_posix()
    assert imported["disposition"] == "applied" and imported["task_id"] == task_id
    private = task.root / ".aoe/task-results" / sha(task.request.read_bytes())
    assert {"task.md", "commits.txt", "diffstat.txt", "review.md", "contract.json"} <= imported[
        "files"
    ].keys()
    for name, digest in imported["files"].items():
        assert sha((private / name).read_bytes()) == digest
    before = tree(task.root)
    invoke(*args, "--confirm", "--confirmed-by", "Replay operator")
    assert tree(task.root) == before and len(task.launched) == 1
    (private / "review.md").write_text("Tampered local artifact\n")
    damaged = tree(task.root)
    invoke(*args, "--confirm", "--confirmed-by", ACTOR, code=1)
    assert tree(task.root) == damaged


def test_import_recovers_published_operational_run_without_allocating_another(task, monkeypatch):
    from toulmin.protocols import engineering_task_import as protocol

    approve(task)
    original = protocol.write_atomic

    def stop(path, data, **kwargs):
        if path.name == "import.json" and json.loads(data).get("disposition") == "applied":
            raise OSError("fixture crash after Run publication")
        return original(path, data, **kwargs)

    args = (
        "task",
        "import",
        "--workspace",
        task.request,
        "--root",
        task.root,
        "--confirm",
        "--confirmed-by",
        ACTOR,
    )
    with monkeypatch.context() as patch:
        patch.setattr(protocol, "write_atomic", stop)
        invoke(*args, code=1)
    records = list((task.root / "runs").glob("*-task-*-result/run.md"))
    assert len(records) == 1
    raw = records[0].read_bytes()
    invoke(*args)
    assert list((task.root / "runs").glob("*-task-*-result/run.md")) == records
    assert records[0].read_bytes() == raw
