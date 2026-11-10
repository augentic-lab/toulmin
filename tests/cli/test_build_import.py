"""R8 B3: fake Chief state, temporary git repositories, no Chief execution or model calls."""

import json
import os
import subprocess
from dataclasses import asdict, replace

import pytest
from typer.testing import CliRunner

from toulmin.adapters.chief import ChiefClient, load_config
from toulmin.application.aoe import scope_state
from toulmin.application.build import project_map
from toulmin.application.build_import import apply_import, prepare_import
from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.atomic import digest
from toulmin.core.build import BuildReview, BuildTask
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.project_proposals import Outcome, render_outcome
from toulmin.core.proposals import MAX_BYTES
from toulmin.protocols import build_import, project_proposals
from toulmin.protocols.build import BuildFact, build_facts
from toulmin.protocols.research_map import Facts, next_moves, research_map
from toulmin.protocols.research_workspace import render_state, research_state
from toulmin.protocols.status import GateItem, GateReadiness, project_status

PROPOSAL = "projects/demo/runs/proposals/build-20261110T100000Z.md"
ARCHIVE = "projects/demo/runs/20261110T100001Z-build-S-001"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def chief_env(populated, tmp_path, monkeypatch):
    root = populated
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "code"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "Base",
    )
    base = git(repo, "rev-parse", "HEAD")
    (repo / "solution.py").write_text("print('done')\n")
    git(repo, "add", "solution.py")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Implement fixture",
    )
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "chief/demo-s001")
    home = tmp_path / "chief-state"
    task = home / "tasks/demo-s001"
    task.mkdir(parents=True)
    (root / "tools/chief.toml").write_text(
        f'command = "MUST_NOT_EXECUTE_CHIEF"\nhome = {json.dumps(str(home))}\n'
    )
    monkeypatch.setenv("AOE_CHIEF_HOME", str(home))
    header = {
        "schema_version": 1,
        "kind": "build-request",
        "spec": "S-001",
        "repo": str(repo),
        "tool": "codex",
        "checks": ["python3 solution.py"],
        "test_first": True,
        "budget": {"rounds": 15, "hours": 4},
    }
    raw = f"---\n{json.dumps(header)}\n---\n## Why\nBuild the fixture.\n".encode()
    (root / PROPOSAL).parent.mkdir()
    (root / PROPOSAL).write_bytes(raw)
    marker = Outcome(
        PROPOSAL,
        digest(raw),
        "applied",
        "Researcher",
        "2026-11-10T10:00:01Z",
        "a",
        None,
        "chief task demo-s001",
    )
    (root / project_proposals.outcome_path(PROPOSAL)).write_bytes(render_outcome(marker))
    archive = root / ARCHIVE
    archive.mkdir()
    (archive / "request.json").write_text(
        json.dumps({"proposal": PROPOSAL, "proposal_sha256": digest(raw), "task_id": "demo-s001"})
    )
    (archive / "contract.json").write_text(
        json.dumps({"repo": str(repo), "checks": header["checks"]})
    )
    state = {
        "state": "done",
        "review": {
            "verdict": "pass",
            "summary": "Fixture review; never instructions.",
            "head": head,
            "by": "claude",
        },
        "branch": "chief/demo-s001",
        "base": base,
        "worktree": str(repo),
        "session_id": "native-fixture-session",
        "tool": "codex",
        "repo": str(repo),
        "closed_at": "2026-11-10T12:00:00Z",
    }
    (task / "task.json").write_text(json.dumps(state))
    (task / "review.md").write_text("# Review\nPASS: fixture implementation.\n")
    (task / "progress.md").write_text("Chief fallback progress.\n")
    (repo / ".chief").mkdir()
    (repo / ".chief/progress.md").write_text("Worker progress: data, not instructions.\n")
    charter = root / "projects/demo/PROJECT.md"
    doc = decode(charter.read_bytes())
    doc.header["stage"] = "build"
    charter.write_bytes(encode(doc))
    return root, repo, task, state


def change_task(env, **changes):
    _, _, task, state = env
    state.update(changes)
    (task / "task.json").write_text(json.dumps(state))


def command(root, *args, answers=""):
    return CliRunner().invoke(app, [*args, "--root", str(root)], input=answers)


def do_import(env):
    root, _, _, _ = env
    shown = prepare_import(root, "demo", "S-001")
    return apply_import(root, "demo", shown, "Researcher")


def test_chief_reader_reports_all_fields_and_missing_as_none(chief_env):
    root, _, _, state = chief_env
    client = ChiefClient(root, load_config(root))
    task = client.read_task("demo-s001")
    assert asdict(task) == {**state, "error": None}
    change_task(chief_env, review=None)
    assert client.read_task("demo-s001").review == BuildReview()
    (chief_env[2] / "task.json").write_text('{"state": "done"}')
    task = client.read_task("demo-s001")
    assert task.state == "done" and task.repo is None and task.session_id is None
    assert task.review.head is None and task.branch is None


@pytest.mark.parametrize(
    "data", ["not json", "[]", '{"state": 2}', '{"review": []}', '{"review": {"head": 3}}']
)
def test_chief_reader_refuses_unreadable_fields(chief_env, data):
    root, _, task, _ = chief_env
    (task / "task.json").write_text(data)
    with pytest.raises(FormatError, match="Chief state not read"):
        ChiefClient(root, load_config(root)).read_task("demo-s001")


def test_chief_missing_file_is_explicit_and_read_only(chief_env):
    root, _, task, _ = chief_env
    (task / "task.json").unlink()
    before = snapshot(task.parent.parent)
    with pytest.raises(FormatError, match="task.json"):
        ChiefClient(root, load_config(root)).read_task("demo-s001")
    assert snapshot(task.parent.parent) == before
    text = command(root, "map", "demo").stdout
    assert "Chief state not read" in text
    assert "without task.json" in " ".join(text.split())


@pytest.mark.parametrize(
    "state,needle",
    [
        ("running", "is running for S-001; keep `chief watch` running"),
        ("needs-you", "chief inbox"),
        ("review", "chief close"),
        ("done", "Import the result"),
        ("abandoned", "import it as failed or re-request"),
        (None, None),
    ],
)
def test_build_rows_for_injected_states_and_move_limit(chief_env, state, needle):
    root, _, _, _ = chief_env
    change_task(chief_env, state=state)
    task = ChiefClient(root, load_config(root)).read_task("demo-s001")
    facts = Facts(
        "build",
        False,
        (),
        0,
        (),
        (),
        (),
        True,
        True,
        builds=build_facts(root, "demo", {"demo-s001": task}),
    )
    moves = next_moves(facts)
    if needle:
        actor = "either" if state == "running" else "you"
        assert any(needle in move.text and move.actor == actor for move in moves)
    else:
        assert not any("Chief task" in move.text for move in moves)
    crowded = replace(
        facts,
        proposals=3,
        gates=(GateReadiness("G1", "critique", False, (GateItem("missing", False, ""),)),),
        handoff_due="build",
    )
    assert len(next_moves(crowded)) <= 3
    assert next_moves(crowded)[0].text == "Run `toulmin decide` for 3 pending proposal(s)."


def test_build_facts_and_offline_map_never_read_chief(chief_env, monkeypatch):
    root, _, _, _ = chief_env

    def no_external(*args, **kwargs):
        raise AssertionError("L2 attempted an external state read")

    monkeypatch.setattr(ChiefClient, "read_task", no_external)
    (fact,) = build_facts(root, "demo")
    assert fact.request == PROPOSAL and fact.task_id == "demo-s001" and not fact.imported
    report = research_map(root, "demo")
    spec = next(node for node in report.claims[0].children if node.object_id == "S-001")
    assert "Chief state not read" in spec.children[0].summary
    assert "Chief state not read" in render_state(research_state(root, "demo"))


def test_map_cli_and_aoe_card_inject_current_task_state(chief_env):
    root, _, _, _ = chief_env
    change_task(chief_env, state="running")
    before = snapshot(root)
    result = command(root, "map", "demo")
    assert result.exit_code == 0, result.output
    assert "Chief task demo-s001" in result.stdout and "running; review pass" in result.stdout
    assert "running; review pass" in render_state(scope_state(root, "demo"))
    expected = "Chief task demo-s001 is running for S-001; keep `chief watch` running"
    assert expected in result.stdout
    assert expected in {move.text for move in scope_state(root, "demo").moves}
    assert snapshot(root) == before


def test_build_stage_suggests_request_only_without_pending_or_applied_request():
    gate = GateReadiness(
        "G3",
        "build",
        True,
        (GateItem("S-001 maps to a Claim with executable acceptance", True, "C-001"),),
    )
    facts = Facts("build", False, (gate,), 0, (), (), (), True, True, builds=(BuildFact("S-001"),))
    assert any("Draft a build request for S-001" in move.text for move in next_moves(facts))
    assert not any(
        "Draft a build request" in move.text
        for move in next_moves(replace(facts, builds=(BuildFact("S-001", pending=True),)))
    )


def test_import_preview_and_apply_done_archive_run_and_drafts(chief_env):
    root, repo, task, state = chief_env
    before_root, before_chief = snapshot(root), snapshot(task.parent.parent)
    result = command(root, "build", "import", "demo", "S-001")
    assert result.exit_code == 0, result.output
    assert "Chief result ready: S-001 (demo-s001, done, review pass)" in result.stdout
    assert snapshot(root) == before_root and snapshot(task.parent.parent) == before_chief
    record = do_import(chief_env)
    (fact,) = build_facts(root, "demo")
    assert fact.imported and record.run == "R-002"
    archive = root / fact.archive
    assert state["review"]["head"] in (archive / "task.md").read_text()
    assert "Implement fixture" in (archive / "commits.txt").read_text()
    assert "solution.py" in (archive / "diffstat.txt").read_text()
    assert (archive / "review.md").read_bytes() == (task / "review.md").read_bytes()
    assert (archive / "progress.md").read_bytes() == (task / "progress.md").read_bytes()
    assert f"progress_source: {task / 'progress.md'}" in (archive / "task.md").read_text()
    run = decode((root / "projects/demo/runs/R-002.md").read_bytes())
    assert run.header["role"] == "implementer" and run.header["status"] == "completed"
    assert run.header["session_id"] == "native-fixture-session"
    assert run.header["model"] == "codex (Chief worker; model not reported)"
    assert run.header["input_files"] == ["projects/demo/specs/S-001.md"]
    assert len(record.proposals) == 3
    evidence = decode((root / "projects/demo/runs/proposals" / record.proposals[1]).read_bytes())
    assert evidence.header["target"] == "C-001" and evidence.header["grade"] == "model-asserted"
    assert len(evidence.header["provenance"]) == 2
    assert state["review"]["head"] in evidence.body
    assert snapshot(task.parent.parent) == before_chief
    assert do_import(chief_env) == record
    assert len(list((root / "projects/demo/runs").glob("R-*.md"))) == 2


def test_abandoned_import_is_a_failed_run_without_proposals(chief_env):
    root, _, _, _ = chief_env
    change_task(chief_env, state="abandoned")
    record = do_import(chief_env)
    assert record.proposals == ()
    run = decode((root / "projects/demo/runs" / f"{record.run}.md").read_bytes())
    assert run.header["status"] == "failed" and "abandoned" in run.body
    assert not project_proposals.inventory(root, "demo").items


def test_full_decide_pass_import_decision_evidence_ruling_makes_g4_hold(chief_env):
    root, _, _, _ = chief_env
    result = command(
        root, "decide", "--confirmed-by", "Researcher", "--no-notify", answers="a\na\na\na\n"
    )
    assert result.exit_code == 0, result.output
    assert "Chief result ready: S-001" in result.stdout
    assert (
        result.stdout.index("Object draft: projects/demo/runs/proposals/decision-")
        < result.stdout.index("Object draft: projects/demo/runs/proposals/evidence-")
        < result.stdout.index("Ruling proposal: projects/demo/runs/proposals/ruling-")
    )
    spec = decode((root / "projects/demo/specs/S-001.md").read_bytes())
    assert spec.header["status"] == "awaiting-acceptance"
    assert spec.header["evidence"] == ["E-002"] and spec.header["decisions"] == ["D-002"]
    assert next(gate for gate in project_status(root, "demo").gates if gate.gate == "G4").met
    assert not next(gate for gate in project_status(root, "demo").gates if gate.gate == "G5").met
    assert "Applied: 4" in result.stdout


@pytest.mark.parametrize("crash_at", ["run", "proposal", "receipt"])
def test_interrupted_import_resumes_without_duplicate_run_or_proposals(
    chief_env, monkeypatch, crash_at
):
    root, _, task, _ = chief_env
    original_publish, original_write = build_import.publish_locked, build_import.write_atomic
    fired = False

    def publish(*args, **kwargs):
        result = original_publish(*args, **kwargs)
        if crash_at == "run":
            raise KeyboardInterrupt
        return result

    def write(path, data, **kwargs):
        nonlocal fired
        original_write(path, data, **kwargs)
        if not fired and (
            (crash_at == "proposal" and path.name.startswith("evidence-"))
            or (crash_at == "receipt" and path.name == "import.json" and b'"applied"' in data)
        ):
            fired = True
            raise KeyboardInterrupt

    monkeypatch.setattr(build_import, "publish_locked", publish)
    monkeypatch.setattr(build_import, "write_atomic", write)
    with pytest.raises(KeyboardInterrupt):
        do_import(chief_env)
    monkeypatch.setattr(build_import, "publish_locked", original_publish)
    monkeypatch.setattr(build_import, "write_atomic", original_write)
    (task / "task.json").unlink()  # replay uses the frozen workspace record, even offline
    record = apply_import(root, "demo", prepare_import(root, "demo", "S-001"), "Another researcher")
    assert record.actor == "Researcher"
    assert record.disposition == "applied" and record.run == "R-002"
    assert len(record.proposals) == 3
    assert len(list((root / "projects/demo/runs").glob("R-*.md"))) == 2
    assert len(project_proposals.inventory(root, "demo").items) == 3


def test_unapplied_evidence_draft_link_is_refused(chief_env):
    root, _, _, _ = chief_env
    record = do_import(chief_env)
    paths = [f"projects/demo/runs/proposals/{name}" for name in record.proposals]
    decision = project_proposals.preview(root, "demo", paths[0])
    project_proposals.apply(root, "demo", paths[0], "Researcher", decision.sha256, "a")
    before = snapshot(root)
    ruling = project_proposals.preview(root, "demo", paths[2])
    assert "evidence: proposal" in " ".join(ruling.problems)
    assert "not decided yet" in " ".join(ruling.problems)
    with pytest.raises(FormatError):
        project_proposals.apply(root, "demo", paths[2], "Researcher", ruling.sha256, "a")
    assert snapshot(root) == before


def test_import_branch_tip_is_used_only_without_review_head(chief_env):
    root, repo, _, state = chief_env
    pinned = state["review"]["head"]
    (repo / "later.txt").write_text("later commit\n")
    git(repo, "add", "later.txt")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Later change",
    )
    tip = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "-f", "chief/demo-s001", tip)
    shown = prepare_import(root, "demo", "S-001")
    assert shown.record.head == pinned
    assert "Later change" not in shown.files["commits.txt"].decode()
    change_task(chief_env, review={"verdict": "pass"})
    shown = prepare_import(root, "demo", "S-001")
    assert shown.record.head == tip and "Later change" in shown.files["commits.txt"].decode()


def test_removed_worktree_uses_chief_progress_and_repository_history(chief_env):
    root, _, task, state = chief_env
    change_task(chief_env, worktree=str(task / "removed-worktree"))
    record = do_import(chief_env)
    (fact,) = build_facts(root, "demo")
    archive = root / fact.archive
    assert (archive / "progress.md").read_bytes() == (task / "progress.md").read_bytes()
    assert record.head == state["review"]["head"]
    assert "Implement fixture" in (archive / "commits.txt").read_text()


def test_missing_task_metadata_is_not_reported_not_guessed(chief_env):
    root, _, task, _ = chief_env
    (task / "task.json").write_text('{"state": "done"}')
    (task / "review.md").unlink()
    (task / "progress.md").unlink()
    record = do_import(chief_env)
    assert record.head is None and record.verdict is None and record.tool is None
    (fact,) = build_facts(root, "demo")
    archive = root / fact.archive
    assert "not reported" in (archive / "task.md").read_text()
    assert (archive / "review.md").read_text() == "Chief review text: not reported.\n"
    run = decode((root / "projects/demo/runs/R-002.md").read_bytes())
    assert run.header["session_id"] is None
    assert run.header["model"] == "not reported (Chief worker; model not reported)"
    assert "base or head not reported" in (archive / "commits.txt").read_text()


@pytest.mark.parametrize("state", ["running", "needs-you", "review", None])
def test_unfinished_task_import_refuses_without_writes(chief_env, state):
    root, _, _, _ = chief_env
    change_task(chief_env, state=state)
    before = snapshot(root)
    result = command(
        root, "build", "import", "demo", "S-001", "--confirm", "--confirmed-by", "Researcher"
    )
    assert result.exit_code == 1 and "import needs done or abandoned" in result.output
    assert snapshot(root) == before


@pytest.mark.parametrize("damage", ["task", "spec"])
def test_stale_import_preview_refuses_without_writes(chief_env, damage):
    root, _, _, _ = chief_env
    shown = prepare_import(root, "demo", "S-001")
    if damage == "task":
        change_task(chief_env, review={"verdict": "needs-changes"})
    else:
        path = root / "projects/demo/specs/S-001.md"
        doc = decode(path.read_bytes())
        # A different current target is a material source change for the generated Evidence.
        claim = decode((root / "projects/demo/claims/C-001.md").read_bytes())
        claim.header["id"] = "C-002"
        (root / "projects/demo/claims/C-002.md").write_bytes(encode(claim))
        doc.header["target"] = "C-002"
        path.write_bytes(encode(doc))
    before = snapshot(root)
    with pytest.raises(FormatError, match="changed since preview"):
        apply_import(root, "demo", shown, "Researcher")
    assert snapshot(root) == before


def test_import_targets_current_claim_and_preserves_researcher_ruling_boundary(chief_env):
    root, _, _, _ = chief_env
    path = root / "projects/demo/claims/C-001.md"
    old = decode(path.read_bytes())
    current = decode(path.read_bytes())
    current.header["id"] = "C-002"
    current.body = "## Statement\nThe revised Claim.\n"
    (path.parent / "C-002.md").write_bytes(encode(current))
    old.header.update(status="superseded", superseded_by="C-002", decisions=["D-001"])
    path.write_bytes(encode(old))
    spec_path = root / "projects/demo/specs/S-001.md"
    before = spec_path.read_bytes()
    record = do_import(chief_env)
    evidence = decode((root / "projects/demo/runs/proposals" / record.proposals[1]).read_bytes())
    assert evidence.header["target"] == "C-002"
    assert spec_path.read_bytes() == before
    assert not any(
        move.text.startswith("Import the result") for move in project_map(root, "demo").moves
    )


def test_import_refuses_changed_archived_material(chief_env):
    root, _, _, _ = chief_env
    do_import(chief_env)
    (fact,) = build_facts(root, "demo")
    (root / fact.archive / "task.md").write_text("edited\n")
    before = snapshot(root)
    with pytest.raises(FormatError, match="artifact changed"):
        do_import(chief_env)
    assert snapshot(root) == before


def test_receipt_with_missing_run_is_reported_as_corrupt(chief_env):
    root, _, _, _ = chief_env
    record = do_import(chief_env)
    (root / f"projects/demo/runs/{record.run}.md").unlink()
    with pytest.raises(FormatError):
        build_facts(root, "demo")


def test_latest_applied_request_and_import_marker_are_derived_from_files(chief_env):
    root, _, _, _ = chief_env
    do_import(chief_env)
    raw = (root / PROPOSAL).read_bytes().replace(b"Build the fixture.", b"Build it again.")
    relative = PROPOSAL.replace("100000Z", "130000Z")
    (root / relative).write_bytes(raw)
    outcome = Outcome(
        relative,
        digest(raw),
        "applied",
        "Researcher",
        "2026-11-10T13:00:01Z",
        "a",
        None,
        "chief task demo-s001",
    )
    (root / project_proposals.outcome_path(relative)).write_bytes(render_outcome(outcome))
    (fact,) = build_facts(root, "demo")
    assert fact.request == relative and not fact.imported and fact.archive is None


def test_map_watch_signature_tracks_external_state_without_writes(chief_env):
    from toulmin.cli.research_map import chief_signature

    root, _, _, _ = chief_env
    before = chief_signature(root, "demo")
    change_task(chief_env, state="needs-you")
    files = snapshot(root)
    assert chief_signature(root, "demo") != before
    assert snapshot(root) == files


@pytest.mark.parametrize("state", ["running", "needs-you", "review", "done", None, "unreadable"])
def test_live_chief_replaces_only_its_specs_generic_g4_work(chief_env, state):
    root, _, _, _ = chief_env
    task = BuildTask(state=state) if state != "unreadable" else BuildTask(error="fixture error")
    gate = GateReadiness(
        "G4",
        "accept",
        False,
        (GateItem("S-001 completion reported with test Evidence", False, ""),),
    )
    facts = Facts(
        "build",
        False,
        (gate,),
        0,
        (),
        (),
        (),
        True,
        True,
        builds=build_facts(root, "demo", {"demo-s001": task}),
    )
    live = state in {"running", "needs-you", "review"}
    assert any(move.text.startswith("Work toward G4:") for move in next_moves(facts)) is not live
    mixed = replace(
        facts,
        gates=(
            replace(gate, items=(*gate.items, GateItem("S-002 completion reported", False, ""))),
        ),
    )
    generic = next(
        move for move in next_moves(mixed, 20) if move.text.startswith("Work toward G4:")
    )
    assert "S-002" in generic.text and ("S-001" in generic.text) is not live
    if state == "running":
        imported = replace(facts, builds=(replace(facts.builds[0], imported=True),))
        assert next_moves(imported)[0].actor == "either"
        assert "is running for S-001" in next_moves(imported)[0].text


def test_import_reads_live_worktree_progress_when_task_copy_is_absent(chief_env):
    root, repo, task, _ = chief_env
    (task / "progress.md").unlink()
    progress = repo / ".chief/progress.md"
    (repo / "progress.md").write_text("Obsolete root progress must not be selected.\n")
    before_code, before_chief = snapshot(repo), snapshot(task.parent.parent)
    record = do_import(chief_env)
    (fact,) = build_facts(root, "demo")
    archive = root / fact.archive
    assert (archive / "progress.md").read_bytes() == progress.read_bytes()
    assert f"progress_source: {progress}" in (archive / "task.md").read_text()
    assert record.files["progress.md"] == digest(progress.read_bytes())
    assert snapshot(repo) == before_code and snapshot(task.parent.parent) == before_chief


@pytest.mark.parametrize(
    "damage",
    [
        "relative",
        "file-link",
        "inside-link",
        "directory-link",
        "worktree-link",
        "directory",
        "fifo",
    ],
)
def test_import_refuses_unsafe_worktree_progress_without_writes(chief_env, tmp_path, damage):
    root, repo, task, _ = chief_env
    (task / "progress.md").unlink()
    progress = repo / ".chief/progress.md"
    progress.unlink()
    outside = tmp_path / "outside.md"
    outside.write_text("Data outside the worktree.\n")
    if damage == "relative":
        change_task(chief_env, worktree="relative-worktree")
    elif damage in {"file-link", "inside-link"}:
        target = outside if damage == "file-link" else repo / "inside.md"
        target.write_text("Symlink target data.\n")
        progress.symlink_to(target)
    elif damage == "directory-link":
        progress.parent.rmdir()
        progress.parent.symlink_to(tmp_path)
    elif damage == "worktree-link":
        alias = tmp_path / "worktree-alias"
        alias.symlink_to(repo, target_is_directory=True)
        change_task(chief_env, worktree=str(alias))
    elif damage == "directory":
        progress.mkdir()
    else:
        os.mkfifo(progress)
    before_root, before_repo, before_chief = (
        snapshot(root),
        snapshot(repo),
        snapshot(task.parent.parent),
    )
    result = command(
        root, "build", "import", "demo", "S-001", "--confirm", "--confirmed-by", "Researcher"
    )
    assert result.exit_code == 1, result.output
    assert snapshot(root) == before_root and snapshot(repo) == before_repo
    assert snapshot(task.parent.parent) == before_chief
    assert not list((root / "projects/demo/runs").glob("*-build-S-001-result"))


@pytest.mark.parametrize("source", ["task", "worktree", "review"])
def test_import_bounds_all_external_text_without_truncation(chief_env, source):
    root, repo, task, _ = chief_env
    path = task / ("review.md" if source == "review" else "progress.md")
    if source == "worktree":
        path.unlink()
        path = repo / ".chief/progress.md"
    path.write_bytes(b"x" * (MAX_BYTES + 1))
    before = snapshot(root)
    with pytest.raises(FormatError, match=f"exceeds {MAX_BYTES} bytes"):
        prepare_import(root, "demo", "S-001")
    assert snapshot(root) == before


def test_import_refuses_a_symlink_task_copy_instead_of_falling_back(chief_env, tmp_path):
    root, _, task, _ = chief_env
    path = task / "progress.md"
    path.unlink()
    target = tmp_path / "target.md"
    target.write_text("Not a regular task copy.\n")
    path.symlink_to(target)
    before = snapshot(root)
    with pytest.raises(FormatError, match="without symlinks"):
        prepare_import(root, "demo", "S-001")
    assert snapshot(root) == before


def test_incomplete_import_resumes_via_decide_and_refuses_modified_draft(chief_env, monkeypatch):
    root, _, task, _ = chief_env
    original = build_import.write_atomic

    def crash(path, data, **kwargs):
        original(path, data, **kwargs)
        if path.name.startswith("decision-"):
            raise KeyboardInterrupt

    monkeypatch.setattr(build_import, "write_atomic", crash)
    with pytest.raises(KeyboardInterrupt):
        do_import(chief_env)
    monkeypatch.setattr(build_import, "write_atomic", original)
    (task / "task.json").unlink()
    draft = next((root / "projects/demo/runs/proposals").glob("decision-*-build-S-001.md"))
    saved = draft.read_bytes()
    draft.write_text("modified\n")
    with pytest.raises(FormatError, match="differs"):
        do_import(chief_env)
    draft.write_bytes(saved)
    result = command(
        root, "decide", "--confirmed-by", "Researcher", "--no-notify", answers="a\na\na\na\n"
    )
    assert result.exit_code == 0, result.output
    assert "Imported Chief task demo-s001 as R-002" in result.stdout
    assert len(list((root / "projects/demo/runs").glob("R-*.md"))) == 2
