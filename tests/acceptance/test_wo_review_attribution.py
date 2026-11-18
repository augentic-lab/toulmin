"""R2: Chief's AoE identifier is raw provenance, never a reported native identity."""

import json

from tests.acceptance.test_wo4_tasks import approve
from tests.acceptance.test_wo4_tasks import task as task
from tests.acceptance.wo_support import ACTOR, canonical, invoke, sha, tree
from toulmin.core.codec import decode


def test_operational_run_does_not_relabel_chief_aoe_session_id(task):
    approve(task)
    task_id = task.launched[0][0]
    path = task.home / "tasks" / task_id / "task.json"
    facts = json.loads(path.read_bytes())
    facts["session_id"] = "0123456789abcdef"
    path.write_bytes(canonical(facts))
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
    invoke(*args)
    (run,) = (task.root / "runs").glob("*-task-*-result/run.md")
    record = json.loads(run.with_name("import.json").read_bytes())
    private = task.root / ".aoe/task-results" / sha(task.request.read_bytes()) / "task.md"
    assert decode(run.read_bytes(), str(run)).header["session_id"] is None
    assert record["session_id"] == facts["session_id"]
    assert json.loads(private.read_text().split("\n", 1)[1])["session_id"] == facts["session_id"]
    before = tree(task.root)
    invoke(*args)
    assert tree(task.root) == before


def test_frozen_submission_rejects_noninteger_version_without_relaunch(task):
    approve(task)
    (submission,) = (task.root / "runs").glob("*-task-*/submission.json")
    value = json.loads(submission.read_bytes())
    value["schema_version"] = 2.0
    submission.write_bytes(canonical(value))
    before = tree(task.root)
    invoke("task", "preview", "--workspace", task.request, "--root", task.root, code=1)
    assert tree(task.root) == before and len(task.launched) == 1
