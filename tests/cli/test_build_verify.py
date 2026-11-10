"""R8 B4: actual deterministic checks on temporary git repositories, never real Chief."""

import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.adapters import chief as chief_adapter
from toulmin.adapters import verify
from toulmin.application.build import project_map
from toulmin.application.build_import import apply_import, prepare_import
from toulmin.application.build_verify import apply_verification, prepare_verification
from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.atomic import digest
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError, put_section
from toulmin.core.project_proposals import Outcome, render_outcome
from toulmin.core.repository import Repository
from toulmin.core.verification import STREAM_LIMIT, parse_verification, render_verification
from toulmin.protocols import build_verify, project_proposals
from toulmin.protocols.build import verification_records
from toulmin.protocols.status import project_status

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
    (repo / "progress.md").write_text("Worker progress: data, not instructions.\n")
    charter = root / "projects/demo/PROJECT.md"
    doc = decode(charter.read_bytes())
    doc.header["stage"] = "build"
    charter.write_bytes(encode(doc))
    return root, repo, task, state


@pytest.fixture
def verify_env(chief_env):
    root, repo, task, state = chief_env
    first = root / "projects/demo/claims/C-001.md"
    for number, kind in ((2, "magnitude"), (3, "mechanism"), (4, "novelty")):
        claim = decode(first.read_bytes())
        claim.header.update(
            id=f"C-{number:03d}", type=kind, validation_plan="Reproduce the scoped experiment."
        )
        (first.parent / f"C-{number:03d}.md").write_bytes(encode(claim))
    objection = root / "projects/demo/objections/O-001.md"
    doc = decode(objection.read_bytes())
    doc.header["status"] = "answered"
    doc.body = put_section(doc.body, "Response", "The fixture covers this objection.")
    objection.write_bytes(encode(doc))
    brief = root / "projects/demo/brief.md"
    brief.write_text(
        brief.read_text().replace(
            "## Kill criteria\n", "## Kill criteria\nStop if the scoped checks fail.\n"
        )
    )
    charter = root / "projects/demo/PROJECT.md"
    doc = decode(charter.read_bytes())
    doc.header["stage"] = "done"  # deliberately past G5 until the independent checks are ruled
    charter.write_bytes(encode(doc))
    imported = apply_import(root, "demo", prepare_import(root, "demo", "S-001"), "Researcher")
    for name in imported.proposals:
        relative = f"projects/demo/runs/proposals/{name}"
        shown = project_proposals.preview(root, "demo", relative)
        assert not shown.problems, shown.problems
        project_proposals.apply(root, "demo", relative, "Researcher", shown.sha256, "a")
    report = project_status(root, "demo")
    assert next(gate for gate in report.gates if gate.gate == "G4").met, report.errors
    return root, repo, task, state


def command(root, *args, answers=""):
    return CliRunner().invoke(app, [*args, "--root", str(root)], input=answers)


def checks(env, commands):
    root = env[0]
    path = root / ARCHIVE / "contract.json"
    data = json.loads(path.read_bytes())
    data["checks"] = commands
    path.write_text(json.dumps(data))


def execute(env, actor="Researcher"):
    root = env[0]
    return apply_verification(root, "demo", prepare_verification(root, "demo", "S-001"), actor)


def result_archive(root):
    return verification_records(Repository(root), "demo")[-1][0]


def test_verify_preview_lists_frozen_inputs_and_execution_warning_without_writes(verify_env):
    root, repo, task, state = verify_env
    before, code, chief = snapshot(root), snapshot(repo), snapshot(task.parent.parent)
    result = command(root, "build", "verify", "demo", "S-001")
    assert result.exit_code == 0, result.output
    assert (
        f"Verify S-001 at {state['review']['head'][:12]}: 1 check(s) in a fresh clone"
        in result.stdout
    )
    assert "python3 solution.py" in result.stdout and str(repo) in result.stdout
    assert "Timeout per check: 600 seconds" in result.stdout
    assert (
        "runs code written by an AI worker on this machine, as you, without network isolation"
        in result.stdout
    )
    assert (
        snapshot(root) == before
        and snapshot(repo) == code
        and snapshot(task.parent.parent) == chief
    )
    assert any(item.kind == "build-verify" for item in decide.inventory(root).items)
    assert any(
        move.text == "Verify S-001 in `toulmin decide`" and move.actor == "you"
        for move in project_map(root, "demo").moves
    )


def test_full_decide_verify_pass_proposes_and_applies_g5_without_stage_warnings(verify_env):
    root, repo, task, state = verify_env
    assert project_status(root, "demo").stage_warnings
    original, refs, worktrees, chief = (
        snapshot(repo),
        git(repo, "show-ref"),
        git(repo, "worktree", "list", "--porcelain"),
        snapshot(task.parent.parent),
    )
    result = command(
        root, "decide", "--confirmed-by", "Researcher", "--no-notify", answers="a\na\na\na\n"
    )
    assert result.exit_code == 0, result.output
    assert "Verification passed: R-003" in result.stdout and "Applied: 4" in result.stdout
    assert (
        result.stdout.index("Object draft: projects/demo/runs/proposals/decision-")
        < result.stdout.index("Object draft: projects/demo/runs/proposals/evidence-")
        < result.stdout.index("Ruling proposal: projects/demo/runs/proposals/ruling-")
    )
    report = project_status(root, "demo")
    assert next(gate for gate in report.gates if gate.gate == "G5").met
    assert not report.stage_warnings and report.stage == "done"
    spec = decode((root / "projects/demo/specs/S-001.md").read_bytes())
    assert spec.header["status"] == "passed" and spec.header["evidence"] == ["E-002", "E-003"]
    run = decode((root / "projects/demo/runs/R-003.md").read_bytes())
    assert run.header["role"] == "verifier" and run.header["status"] == "completed"
    assert run.header["model"] == "none (deterministic re-run by toulmin)"
    assert run.header["source"] == {"kind": "human", "actor": "Researcher"}
    assert run.header["input_files"] == ["projects/demo/specs/S-001.md", ARCHIVE + "/contract.json"]
    evidence = decode((root / "projects/demo/evidence/E-003.md").read_bytes())
    assert evidence.header["grade"] == "verified" and evidence.header["target"] == "C-001"
    assert (
        evidence.header["verification"]["method"]
        == f"re-ran the frozen S-001 checks in a fresh clone at {state['review']['head']}"
    )
    archive = root / run.header["output"]
    assert evidence.header["verification"]["artifacts"] == [
        run.header["output"] + "/output.md",
        run.header["output"] + "/environment.txt",
    ]
    assert "Exit status: 0" in (archive / "output.md").read_text()
    for value in ("OS:", "Python:", "Git:", str(repo), state["review"]["head"]):
        assert value in (archive / "environment.txt").read_text()
    assert snapshot(repo) == original and git(repo, "show-ref") == refs
    assert git(repo, "worktree", "list", "--porcelain") == worktrees
    assert snapshot(task.parent.parent) == chief
    assert not any(item.kind == "build-verify" for item in decide.inventory(root).items)


def test_failing_check_archives_completed_run_without_proposals_and_failure_row(verify_env):
    root, repo, _, state = verify_env
    checks(verify_env, ["echo fixture-failure >&2; exit 3", "echo continued-after-failure"])
    original = snapshot(repo)
    result = command(
        root, "build", "verify", "demo", "S-001", "--confirm", "--confirmed-by", "Researcher"
    )
    assert result.exit_code == 1, result.output
    records = verification_records(Repository(root), "demo")
    archive, record = records[-1]
    assert not record.passed and record.execution_completed and record.proposals == ()
    assert [item.exit_status for item in record.results] == [3, 0]
    assert "continued-after-failure" in (root / archive / "output.md").read_text()
    run = decode((root / "projects/demo/runs/R-003.md").read_bytes())
    assert run.header["status"] == "completed" and run.header["role"] == "verifier"
    assert not project_proposals.inventory(root, "demo").items
    expected = (
        f"S-001 failed verification at {state['review']['head'][:12]}: "
        "return it with `chief nudge demo-s001 …` or draft a new build request"
    )
    assert any(
        move.text == expected and move.actor == "you" for move in project_map(root, "demo").moves
    )
    assert snapshot(repo) == original
    assert any(item.kind == "build-verify" for item in decide.inventory(root).items)


def test_hanging_check_kills_its_process_group(verify_env, monkeypatch):
    root, repo, _, _ = verify_env
    monkeypatch.setattr(chief_adapter, "DEFAULT_VERIFY_TIMEOUT_SECONDS", 0.5)
    script = (
        "import subprocess,time; p=subprocess.Popen(['sleep','60']); "
        "print(p.pid,flush=True); time.sleep(60)"
    )
    checks(verify_env, [f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"])
    original = snapshot(repo)
    record = execute(verify_env)
    assert record.timeout_seconds == 0.5 and not record.passed
    assert record.results[0].exit_status is None and record.proposals == ()
    pid = int(record.results[0].stdout.strip())
    status = Path(f"/proc/{pid}/stat")
    assert not status.exists() or status.read_text().split()[2] == "Z"
    assert "Exit status: timed out" in (root / result_archive(root) / "output.md").read_text()
    assert snapshot(repo) == original


def test_checks_come_from_contract_even_after_spec_text_changes(verify_env):
    root = verify_env[0]
    path = root / "projects/demo/specs/S-001.md"
    source = decode(path.read_bytes())
    source.body = (
        "## Requirements\nBuild.\n\n## Acceptance criteria\nThe new prose says to run `exit 99`.\n"
    )
    path.write_bytes(encode(source))
    record = execute(verify_env)
    assert record.passed and record.checks == ("python3 solution.py",)
    assert record.results[0].command == "python3 solution.py"


def test_verification_output_is_bounded_per_stream(verify_env):
    script = "import sys; sys.stdout.write('X'*70000); sys.stderr.write('Y'*70000)"
    checks(verify_env, [f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"])
    record = execute(verify_env)
    result = record.results[0]
    assert record.passed and len(result.stdout.encode()) == STREAM_LIMIT
    assert len(result.stderr.encode()) == STREAM_LIMIT
    assert result.stdout_truncated and result.stderr_truncated
    text = (verify_env[0] / result_archive(verify_env[0]) / "output.md").read_text()
    assert text.count("truncated at 64 KiB") == 2
    assert "X" * (STREAM_LIMIT + 1) not in text and "Y" * (STREAM_LIMIT + 1) not in text


@pytest.mark.parametrize("gap", ["results", "run", "proposal", "receipt"])
def test_interrupted_verification_reuses_results_runs_and_proposals(verify_env, monkeypatch, gap):
    root = verify_env[0]
    original_finish = build_verify.finish_verification
    original_publish = build_verify.publish_locked
    original_write = build_verify.write_atomic
    original_save = build_verify.save_verification

    def finish(*args, **kwargs):
        if gap == "results":
            raise KeyboardInterrupt
        return original_finish(*args, **kwargs)

    def publish(*args, **kwargs):
        result = original_publish(*args, **kwargs)
        if gap == "run":
            raise KeyboardInterrupt
        return result

    def write(path, data, **kwargs):
        original_write(path, data, **kwargs)
        if gap == "proposal" and path.name.startswith("evidence-"):
            raise KeyboardInterrupt

    def save(repository, archive, record):
        original_save(repository, archive, record)
        if gap == "receipt" and record.disposition == "applied":
            raise KeyboardInterrupt

    monkeypatch.setattr(build_verify, "finish_verification", finish)
    monkeypatch.setattr(build_verify, "publish_locked", publish)
    monkeypatch.setattr(build_verify, "write_atomic", write)
    monkeypatch.setattr(build_verify, "save_verification", save)
    with pytest.raises(KeyboardInterrupt):
        execute(verify_env)
    monkeypatch.setattr(build_verify, "finish_verification", original_finish)
    monkeypatch.setattr(build_verify, "publish_locked", original_publish)
    monkeypatch.setattr(build_verify, "write_atomic", original_write)
    monkeypatch.setattr(build_verify, "save_verification", original_save)

    def no_rerun(*args, **kwargs):
        raise AssertionError("completed verification executed again")

    monkeypatch.setattr(verify, "run_checks", no_rerun)
    done = execute(verify_env, "Another researcher")
    assert done.actor == "Researcher" and done.passed and done.run == "R-003"
    assert len(done.proposals) == 3
    assert len(verification_records(Repository(root), "demo")) == 1
    assert len(list((root / "projects/demo/runs").glob("R-*.md"))) == 3
    assert len(project_proposals.inventory(root, "demo").items) == 3


def test_partial_execution_is_preserved_and_restarted_in_a_new_clone(verify_env, monkeypatch):
    root = verify_env[0]
    checks(verify_env, ["pwd", "echo second"])
    original = verify.run_check
    calls = 0

    def interrupt(command, clone, timeout):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return original(command, clone, timeout)

    monkeypatch.setattr(verify, "run_check", interrupt)
    with pytest.raises(KeyboardInterrupt):
        execute(verify_env)
    archive, pending = verification_records(Repository(root), "demo")[0]
    first_clone = Path(pending.results[0].stdout.strip())
    assert not first_clone.exists() and not pending.execution_completed
    monkeypatch.setattr(verify, "run_check", original)
    done = execute(verify_env)
    assert done.passed and done.previous == (pending.snapshot,)
    assert Path(done.results[0].stdout.strip()) != first_clone
    assert not Path(done.results[0].stdout.strip()).exists()
    assert (root / archive / pending.snapshot / "output.md").is_file()
    assert done.run == "R-003" and len(verification_records(Repository(root), "demo")) == 1


def test_clone_is_outside_workspace_even_when_tmpdir_is_inside_it(verify_env, monkeypatch):
    root, repo, _, _ = verify_env
    parent = root / "tmp"
    parent.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(parent))
    checks(verify_env, ["pwd"])
    original = snapshot(repo)
    done = execute(verify_env)
    clone = Path(done.results[0].stdout.strip())
    assert not clone.is_relative_to(root) and not clone.is_relative_to(repo)
    assert not clone.exists() and snapshot(repo) == original


def test_passing_head_is_not_verified_or_proposed_twice(verify_env, monkeypatch):
    root = verify_env[0]
    first = execute(verify_env)
    before = snapshot(root)

    def no_rerun(*args, **kwargs):
        raise AssertionError("passing head executed again")

    monkeypatch.setattr(verify, "run_checks", no_rerun)
    assert execute(verify_env) == first
    assert snapshot(root) == before
    assert not any(item.kind == "build-verify" for item in decide.inventory(root).items)


@pytest.mark.parametrize("damage", ["contract", "spec", "timeout"])
def test_changed_preview_inputs_refuse_without_writes(verify_env, damage):
    root = verify_env[0]
    shown = prepare_verification(root, "demo", "S-001")
    if damage == "contract":
        checks(verify_env, ["exit 99"])
    elif damage == "spec":
        path = root / "projects/demo/specs/S-001.md"
        path.write_text(path.read_text() + "\nChanged criteria.\n")
    else:
        path = root / "tools/chief.toml"
        path.write_text(path.read_text() + "verify_timeout_seconds = 5\n")
    before = snapshot(root)
    with pytest.raises(FormatError, match="changed since preview"):
        apply_verification(root, "demo", shown, "Researcher")
    assert snapshot(root) == before


@pytest.mark.parametrize("value", [0, -1, True, "600"])
def test_invalid_verification_timeout_is_refused_without_writes(verify_env, value):
    root = verify_env[0]
    path = root / "tools/chief.toml"
    path.write_text(path.read_text() + "verify_timeout_seconds = " + json.dumps(value) + "\n")
    before = snapshot(root)
    result = command(
        root, "build", "verify", "demo", "S-001", "--confirm", "--confirmed-by", "Researcher"
    )
    assert result.exit_code == 1 and "verify_timeout_seconds" in result.output
    assert snapshot(root) == before


def test_verification_checks_out_imported_head_when_source_branch_has_moved(verify_env):
    root, repo, _, state = verify_env
    pinned = state["review"]["head"]
    (repo / "solution.py").write_text("raise SystemExit(9)\n")
    git(repo, "add", "solution.py")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Later failing version",
    )
    assert git(repo, "rev-parse", "HEAD") != pinned
    before = snapshot(repo)
    done = execute(verify_env)
    assert done.passed and done.head == pinned and done.results[0].stdout.strip() == "done"
    assert snapshot(repo) == before
    assert pinned in (root / result_archive(root) / "environment.txt").read_text()


def test_checkpoint_publication_gap_retains_old_pointer_and_can_retry(verify_env, monkeypatch):
    root = verify_env[0]
    original = build_verify.save_verification

    def interrupt(repository, archive, record):
        if record.execution_completed:
            raise KeyboardInterrupt  # immutable snapshot published; journal still points at partial
        original(repository, archive, record)

    monkeypatch.setattr(build_verify, "save_verification", interrupt)
    with pytest.raises(KeyboardInterrupt):
        execute(verify_env)
    archive, record = verification_records(Repository(root), "demo")[0]
    assert not record.execution_completed and not record.passed
    monkeypatch.setattr(build_verify, "save_verification", original)
    done = execute(verify_env)
    assert done.passed and done.run == "R-003" and done.previous == (record.snapshot,)
    assert len(list((root / archive / "checkpoints").iterdir())) >= 2


def test_interrupted_passed_ruling_preserves_prior_evidence_and_replays_without_writes(
    verify_env, monkeypatch
):
    root = verify_env[0]
    done = execute(verify_env)
    paths = [f"projects/demo/runs/proposals/{name}" for name in done.proposals]
    for relative in paths[:2]:
        shown = project_proposals.preview(root, "demo", relative)
        project_proposals.apply(root, "demo", relative, "Researcher", shown.sha256, "a")
    original = project_proposals._write_outcome

    def interrupt(repository, relative, outcome, **kwargs):
        if outcome.disposition == "applied":
            raise KeyboardInterrupt
        original(repository, relative, outcome, **kwargs)

    monkeypatch.setattr(project_proposals, "_write_outcome", interrupt)
    shown = project_proposals.preview(root, "demo", paths[2])
    with pytest.raises(KeyboardInterrupt):
        project_proposals.apply(root, "demo", paths[2], "Researcher", shown.sha256, "a")
    monkeypatch.setattr(project_proposals, "_write_outcome", original)
    spec = root / "projects/demo/specs/S-001.md"
    before = spec.read_bytes()
    recovered = project_proposals.preview(root, "demo", paths[2])
    assert recovered.recovered == "S-001"
    project_proposals.apply(root, "demo", paths[2], "Researcher", recovered.sha256, "a")
    assert spec.read_bytes() == before
    assert decode(before).header["evidence"] == ["E-002", "E-003"]


def test_failed_verification_can_be_retried_without_reusing_its_run(verify_env, monkeypatch):
    marker = verify_env[0].parent / "allow-check"
    checks(verify_env, [f"test -f {shlex.quote(str(marker))}"])
    first = execute(verify_env)
    assert not first.passed and first.run == "R-003"
    marker.touch()
    second = execute(verify_env)
    assert second.passed and second.run == "R-004"
    records = verification_records(Repository(verify_env[0]), "demo")
    assert len(records) == 2 and records[0][0] != records[1][0]
    assert len(project_proposals.inventory(verify_env[0], "demo").items) == 3


@pytest.mark.parametrize("state", ["todo", "in-progress", "failed"])
def test_verify_refuses_wrong_spec_status_without_writes(verify_env, state):
    root = verify_env[0]
    path = root / "projects/demo/specs/S-001.md"
    spec = decode(path.read_bytes())
    spec.header["status"] = state
    path.write_bytes(encode(spec))
    before = snapshot(root)
    with pytest.raises(FormatError, match="awaiting-acceptance"):
        prepare_verification(root, "demo", "S-001")
    assert not any(item.kind == "build-verify" for item in decide.inventory(root).items)
    assert snapshot(root) == before


def test_verify_refuses_import_without_head_and_moved_repository(verify_env):
    root, repo, _, _ = verify_env
    record_path = next((root / "projects/demo/runs").glob("*-build-S-001-result/import.json"))
    original = record_path.read_bytes()
    record = json.loads(original)
    record["head"] = None
    record_path.write_text(json.dumps(record))
    before = snapshot(root)
    with pytest.raises(FormatError, match="head commit"):
        prepare_verification(root, "demo", "S-001")
    assert snapshot(root) == before
    record_path.write_bytes(original)
    repo.rename(repo.with_name("moved-code"))
    before = snapshot(root)
    with pytest.raises(FormatError, match="moved or missing"):
        prepare_verification(root, "demo", "S-001")
    assert snapshot(root) == before


def test_verify_needs_researcher_attribution_and_refuses_blank_checks(verify_env):
    root = verify_env[0]
    before = snapshot(root)
    with pytest.raises(FormatError, match="actor"):
        execute(verify_env, "")
    assert snapshot(root) == before
    checks(verify_env, [])
    before = snapshot(root)
    with pytest.raises(FormatError, match="nonempty"):
        prepare_verification(root, "demo", "S-001")
    assert snapshot(root) == before


@pytest.mark.parametrize("damage", ["checkpoint", "public", "contract"])
def test_corrupt_verification_material_is_refused_without_repair(verify_env, damage):
    root = verify_env[0]
    done = execute(verify_env)
    archive = result_archive(root)
    if damage == "checkpoint":
        path = root / archive / done.snapshot / "output.md"
    elif damage == "public":
        path = root / archive / "environment.txt"
    else:
        path = root / done.contract
    path.write_bytes(path.read_bytes() + b"\nchanged\n")
    before = snapshot(root)
    with pytest.raises(FormatError, match="changed"):
        prepare_verification(root, "demo", "S-001")
    assert snapshot(root) == before


def test_invalid_verification_receipts_are_reported_as_format_errors(verify_env):
    done = execute(verify_env)
    raw = json.loads(render_verification(done))
    raw["results"][0]["command"] = "unfrozen command"
    with pytest.raises(FormatError, match="frozen check"):
        parse_verification(json.dumps(raw).encode(), "fixture")
    raw = json.loads(render_verification(done))
    raw["execution_completed"] = False
    with pytest.raises(FormatError, match="completed execution"):
        parse_verification(json.dumps(raw).encode(), "fixture")
