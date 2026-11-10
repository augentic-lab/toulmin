"""R8 B2: temporary git work trees and a fake Chief; no real Chief/config/network."""

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.adapters import chief as chief_adapter
from toulmin.adapters.chief import ChiefClient, load_config
from toulmin.application.build import apply_build, prepare_build
from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError, sections
from toulmin.core.project_proposals import validate_build_request, validate_outcome
from toulmin.protocols import project_proposals
from toulmin.protocols.build import spec_commands

FOLDER = "projects/demo/runs/proposals"
SPEC = "projects/demo/specs/S-001.md"
NAME = "build-20261110T100000Z.md"
FAKE = """import json, os, pathlib, sys, time
args = sys.argv[1:]
assert args[0] == "new", args
contract = json.loads(pathlib.Path(args[args.index("--from") + 1]).read_text())
tid = args[args.index("--id") + 1]
home = pathlib.Path(os.environ["AOE_CHIEF_HOME"])
with (home / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps({"argv": args, "cwd": os.getcwd(), "contract": contract}) + "\\n")
if (home / "fail").exists():
    print("AoE down: fixture failure", file=sys.stderr)
    sys.exit(7)
if (home / "hang").exists():
    print("Waiting before task creation", flush=True)
    time.sleep(60)
folder = home / "tasks" / tid
folder.mkdir(parents=True)
(folder / "task.json").write_text(json.dumps({"repo": str(pathlib.Path(contract["repo"]).resolve()),
                                           "state": "running", "id": tid}))
print("Created chief task " + tid, flush=True)
print("Needs you: approve tests in chief inbox", file=sys.stderr, flush=True)
if (home / "fail-after-create").exists():
    print("Chief failed after creating the task", file=sys.stderr, flush=True)
    sys.exit(7)
if (home / "hang-after-create").exists():
    time.sleep(60)
"""


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def amend(root, **changes):
    path = root / SPEC
    doc = decode(path.read_bytes())
    doc.header.update(changes)
    path.write_bytes(encode(doc))


@pytest.fixture
def build_env(populated, tmp_path, monkeypatch):
    root = populated
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "code with spaces"
    repo.mkdir()
    for args in (
        ["init", "-b", "main"],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "Fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    home = tmp_path / "chief-state"
    home.mkdir()
    monkeypatch.setenv("AOE_CHIEF_HOME", str(home))
    script = tmp_path / "fake chief.py"
    script.write_text(FAKE)
    config = root / "tools/chief.toml"
    command = shlex.join([sys.executable, str(script)])
    config.write_text(
        f"command = {json.dumps(command)}\nhome = {json.dumps(str(home))}\n"
        f'tool = "claude"\nbudget = {{rounds = 8, hours = 2.5}}\n[repos]\n'
        f"demo = {json.dumps(str(repo))}\n"
    )
    amend(root, status="todo")
    doc = decode((root / SPEC).read_bytes())
    doc.body = (
        "## Requirements\nBuild the fixture.\n\n## Acceptance criteria\nRun `python3 check.py`.\n"
    )
    (root / SPEC).write_bytes(encode(doc))
    return root, repo, home


def request(env, **changes):
    root, repo, _ = env
    header = {
        "schema_version": 1,
        "kind": "build-request",
        "spec": "S-001",
        "repo": str(repo),
        "tool": "codex",
        "checks": ["python3 check.py"],
        "test_first": True,
        "protected": ["tests"],
        "budget": {"rounds": 15, "hours": 4},
        **changes,
    }
    # JSON mappings are valid YAML and keep shell commands quoted exactly.
    raw = (
        f"---\n{json.dumps(header)}\n---\n## Why\nReady to build.\n\n"
        "## Context for the implementer\nUse the fixture trace.\n"
    )
    folder = root / FOLDER
    folder.mkdir(exist_ok=True)
    path = folder / NAME
    path.write_text(raw)
    return path.relative_to(root).as_posix()


def run(root, answers="s\n"):
    return CliRunner().invoke(
        app,
        ["decide", "--root", str(root), "--confirmed-by", "Researcher", "--no-notify"],
        input=answers,
    )


def outcome(root, relative):
    path = root / project_proposals.outcome_path(relative)
    return validate_outcome(decode(path.read_bytes()))


def calls(home):
    path = home / "calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_build_draft_prefills_config_and_commands_without_writing_a_proposal(build_env):
    root, repo, home = build_env
    result = CliRunner().invoke(
        app, ["draft", "build", "demo", "--root", str(root), "--spec", "S-001"]
    )
    assert result.exit_code == 0, result.output
    path = root / result.stdout.strip()
    assert path.parent == root / "projects/demo/runs/drafts"
    assert re.fullmatch(r"build-\d{8}T\d{6}Z.md", path.name)
    doc = decode(path.read_bytes())
    assert doc.header["repo"] == str(repo)
    assert doc.header["checks"] == ["python3 check.py"]
    assert doc.header["tool"] == "claude" and doc.header["budget"] == {"rounds": 8, "hours": 2.5}
    assert doc.header["task_id"] == "demo-s001" and doc.header["test_first"] is True
    assert doc.header["trust"] is False
    text = re.sub(r"## Why\n<fill:[^\n]*", "## Why\nBuild now.", path.read_text())
    assert validate_build_request(decode(text.encode())).spec == "S-001"
    assert not calls(home) and not (root / FOLDER).exists()


def test_build_draft_repo_override_and_absent_config(build_env):
    root, repo, _ = build_env
    (root / "tools/chief.toml").unlink()
    result = CliRunner().invoke(
        app, ["draft", "build", "demo", "--root", str(root), "--spec", "S-001", "--repo", str(repo)]
    )
    assert result.exit_code == 0, result.output
    doc = decode((root / result.stdout.strip()).read_bytes())
    assert doc.header["tool"] == "codex" and doc.header["repo"] == str(repo)
    result = CliRunner().invoke(
        app, ["draft", "build", "demo", "--root", str(root), "--spec", "S-001"]
    )
    assert result.exit_code == 0
    assert "<fill:" in decode((root / result.stdout.strip()).read_bytes()).header["repo"]


@pytest.mark.parametrize(
    "args", [[], ["--spec", "C-001"], ["--spec", "S-999"], ["--spec", "S-001", "--object", "C-001"]]
)
def test_invalid_build_draft_writes_nothing(build_env, args):
    root, _, home = build_env
    before = snapshot(root)
    result = CliRunner().invoke(app, ["draft", "build", "demo", "--root", str(root), *args])
    assert result.exit_code != 0
    assert snapshot(root) == before and not calls(home)


@pytest.mark.parametrize(
    "criteria,expected",
    [
        ("Run `python3 check.py` and ``echo `pwd` ``.\n", ("python3 check.py", "echo `pwd`")),
        ("```sh\npython3 check.py\necho done\n```\n", ("python3 check.py\necho done",)),
        ("~~~bash\npython3 check.py\n~~~\n", ("python3 check.py",)),
        ("```shell\nset -e\npython3 check.py\n```", ("set -e\npython3 check.py",)),
        ("```console\n$ python3 check.py\nPASS\n```", ("python3 check.py",)),
        ("```\nPASS `not a command`\n```\n```json\n{}\n```", ()),
        ("```python\nprint('no')\n```\nRun `echo yes`.\n", ("echo yes",)),
        ("```sh\n# unfinished", ()),
    ],
)
def test_build_spec_command_prefill(criteria, expected):
    assert spec_commands(criteria) == expected


def test_build_preview_shows_full_contract_g3_and_only_approved_context(build_env):
    root, repo, home = build_env
    relative = request(build_env, base_branch="main")
    before = snapshot(root)
    result = run(root)
    assert result.exit_code == 0, result.output
    assert "Full frozen Chief contract" in result.stdout
    assert "Checks match the Spec's commands" in result.stdout
    assert "G3 item [x]: S-001" in result.stdout and "chief watch must be running" in result.stdout
    plan = prepare_build(root, "demo", relative).preview.build
    assert not prepare_build(root, "demo", relative).problems
    contract = plan.contract
    assert contract["repo"] == str(repo) and contract["base_branch"] == "main"
    assert contract["name"] == "demo S-001: Build the fixture."
    spec = decode((root / SPEC).read_bytes())
    claim = decode((root / "projects/demo/claims/C-001.md").read_bytes())
    charter = decode((root / "projects/demo/PROJECT.md").read_bytes())
    for text in (
        sections(spec)["Requirements"],
        sections(spec)["Acceptance criteria"],
        sections(claim)["Statement"],
        sections(charter)["Constraints"],
        "Use the fixture trace.",
    ):
        assert text in contract["goal"]
    assert "Ready to build." not in contract["goal"]
    assert "Deliver on branch chief/demo-s001" in contract["goal"]
    assert set(contract) == {
        "repo",
        "name",
        "goal",
        "checks",
        "protected",
        "test_first",
        "tool",
        "budget",
        "base_branch",
    }
    assert snapshot(root) == before and not calls(home)


def test_build_check_mismatch_is_prominent_but_not_a_refusal(build_env):
    root, _, _ = build_env
    relative = request(build_env, checks=["python3 replacement.py"])
    result = run(root)
    assert "Check mismatch" in result.stdout
    assert "python3 replacement.py" in result.stdout and "python3 check.py" in result.stdout
    assert not prepare_build(root, "demo", relative).problems


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"checks": []}, "checks"),
        ({"checks": ["<fill: command>"]}, "placeholder"),
        ({"repo": "relative"}, "absolute"),
        ({"repo": "/no/such/repo"}, "repository"),
        ({"spec": "S-999"}, "existing regular file"),
        ({"spec": "C-001"}, "spec"),
        ({"task_id": "../escape"}, "task_id"),
        ({"test_first": "true"}, "test_first"),
        ({"budget": {"rounds": 0, "hours": 1}}, "rounds"),
        ({"budget": {"rounds": 1, "hours": False}}, "hours"),
        ({"protected": ["../tests"]}, "protected"),
        ({"tool": "unsupported"}, "tool"),
        ({"base_branch": "--help"}, "base_branch"),
        ({"base_branch": "absent"}, "base_branch"),
        ({"model": "not allowed"}, "unknown field"),
    ],
)
def test_build_validation_refusals_write_nothing(build_env, changes, reason):
    root, _, home = build_env
    relative = request(build_env, **changes)
    before = snapshot(root)
    prepared = prepare_build(root, "demo", relative)
    assert reason in " ".join(prepared.problems)
    with pytest.raises(FormatError):
        apply_build(root, "demo", prepared, "Researcher", "a")
    result = run(root)
    assert "Problem:" in result.stdout
    assert snapshot(root) == before and not calls(home)


@pytest.mark.parametrize(
    "change,reason", [({"status": "awaiting-acceptance"}, "status"), ({"target": "C-999"}, "C-999")]
)
def test_build_spec_state_refusal(build_env, change, reason):
    root, _, home = build_env
    relative = request(build_env)
    amend(root, **change)
    prepared = prepare_build(root, "demo", relative)
    assert reason in " ".join(prepared.problems)
    assert not calls(home)


def test_build_non_git_directory_and_unfilled_draft_refuse(build_env, tmp_path):
    root, _, _ = build_env
    relative = request(build_env, repo=str(tmp_path))
    assert "git work tree" in " ".join(prepare_build(root, "demo", relative).problems)
    relative = request(build_env)
    path = root / relative
    path.write_text(path.read_text().replace("Ready to build.", "<fill: why>"))
    assert "placeholder" in " ".join(prepare_build(root, "demo", relative).problems)


def test_build_apply_archives_calls_chief_and_preserves_formal_files(build_env):
    root, _, home = build_env
    relative = request(build_env, base_branch="main")
    before = snapshot(root)
    result = run(root, "a\n")
    assert result.exit_code == 0, result.output
    done = outcome(root, relative)
    assert done.disposition == "applied" and done.result == "chief task demo-s001"
    assert done.actor == "Researcher" and done.approval_text == "toulmin decide: a"
    (call,) = calls(home)
    assert call["cwd"] == str(root)
    assert call["argv"][-2:] == ["--base-branch", "main"]
    archives = list((root / "projects/demo/runs").glob("*-build-S-001"))
    (archive,) = archives
    assert json.loads((archive / "contract.json").read_bytes()) == call["contract"]
    assert "Created chief task" in (archive / "chief-new.txt").read_text()
    assert "Needs you:" in (archive / "chief-new.txt").read_text()
    for path, raw in before.items():
        assert (root / path).read_bytes() == raw
    assert not project_proposals.inventory(root, "demo").items
    assert run(root).stdout.strip() == "Nothing awaits your decision."


def test_chief_new_failure_is_terminal_with_full_message_and_archive(build_env):
    root, _, home = build_env
    relative = request(build_env)
    (home / "fail").touch()
    result = run(root, "a\n")
    assert result.exit_code == 1, result.output
    done = outcome(root, relative)
    assert done.disposition == "failed" and "AoE down: fixture failure" in done.reason
    assert done.result is None and "archive kept" in result.stdout
    assert "task id demo-s001 is free" in result.stdout
    (archive,) = (root / "projects/demo/runs").glob("*-build-S-001")
    assert "exit status: 7" in (archive / "chief-new.txt").read_text()
    assert not project_proposals.inventory(root, "demo").items
    assert len(calls(home)) == 1


def test_build_recovers_after_chief_new_without_starting_it_twice(build_env, monkeypatch):
    root, _, home = build_env
    relative = request(build_env)
    original = project_proposals.finish_build

    def crash(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(project_proposals, "finish_build", crash)
    prepared = prepare_build(root, "demo", relative)
    with pytest.raises(KeyboardInterrupt):
        apply_build(root, "demo", prepared, "Researcher", "a")
    assert outcome(root, relative).disposition == "applying" and len(calls(home)) == 1
    monkeypatch.setattr(project_proposals, "finish_build", original)
    prepared = prepare_build(root, "demo", relative)
    assert prepared.recovered and not prepared.problems
    result = run(root, "a\n")
    assert result.exit_code == 0, result.output
    assert "apply only records it" in result.stdout
    assert len(calls(home)) == 1 and outcome(root, relative).disposition == "applied"


def test_build_interruption_before_chief_new_can_finish(build_env, monkeypatch):
    root, _, home = build_env
    relative = request(build_env)
    original = ChiefClient.new

    def crash(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ChiefClient, "new", crash)
    with pytest.raises(KeyboardInterrupt):
        apply_build(root, "demo", prepare_build(root, "demo", relative), "Researcher", "a")
    assert outcome(root, relative).disposition == "applying" and not calls(home)
    monkeypatch.setattr(ChiefClient, "new", original)
    assert run(root, "a\n").exit_code == 0
    assert len(calls(home)) == 1


def test_build_existing_task_is_not_adopted_without_own_interruption(build_env):
    root, repo, home = build_env
    relative = request(build_env)
    folder = home / "tasks/demo-s001"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({"repo": str(repo), "state": "running"}))
    prepared = prepare_build(root, "demo", relative)
    assert "already taken" in " ".join(prepared.problems)
    before = snapshot(root)
    assert run(root).exit_code == 0 and snapshot(root) == before and not calls(home)


def test_build_prior_live_task_for_spec_blocks_another_id(build_env):
    root, _, home = build_env
    relative = request(build_env)
    original = root / relative
    original.rename(original.with_name("build-20261110T100000Z-first.md"))
    assert run(root, "a\n").exit_code == 0
    relative = request(build_env, task_id="another-id")
    assert "prior build demo-s001 is live" in " ".join(
        prepare_build(root, "demo", relative).problems
    )
    assert len(calls(home)) == 1


@pytest.mark.parametrize("changed", ["proposal", "spec", "config"])
def test_build_changed_preview_inputs_refuse_without_writing(build_env, changed):
    root, _, home = build_env
    relative = request(build_env)
    prepared = prepare_build(root, "demo", relative)
    path = {"proposal": relative, "spec": SPEC, "config": "tools/chief.toml"}[changed]
    file = root / path
    file.write_text(file.read_text() + "\n# Changed\n")
    before = snapshot(root)
    # Spec contract includes this trailing Acceptance text; config comments keep values the same.
    if changed == "config":
        file.write_text(file.read_text().replace('tool = "claude"', 'tool = "codex"'))
        before = snapshot(root)
    with pytest.raises(FormatError, match="changed"):
        apply_build(root, "demo", prepared, "Researcher", "a")
    assert snapshot(root) == before and not calls(home)


def test_build_empty_actor_refuses_without_any_write(build_env):
    root, _, _ = build_env
    relative = request(build_env)
    before = snapshot(root)
    with pytest.raises(FormatError, match="actor"):
        apply_build(root, "demo", prepare_build(root, "demo", relative), "", "a")
    assert snapshot(root) == before


def test_build_reject_is_recorded_without_starting_chief(build_env):
    root, _, home = build_env
    relative = request(build_env)
    result = run(root, "r\nNeed stronger checks.\n")
    assert result.exit_code == 0
    assert outcome(root, relative).reason == "Need stronger checks."
    assert not calls(home) and not list((root / "projects/demo/runs").glob("*-build-S-001"))


def test_build_config_defaults_do_not_read_chief_config(build_env):
    root, _, home = build_env
    (root / "tools/chief.toml").unlink()
    config = load_config(root)
    assert config.home == home and config.tool == "codex" and config.repos == {}
    assert config.budget == {"rounds": 15, "hours": 4}
    assert config.command == ("python3", str(Path.home() / "aoe-chief/chief.py"))


def test_build_g3_refusal_does_not_apply(build_env):
    root, _, home = build_env
    relative = request(build_env)
    path = root / SPEC
    path.write_text(path.read_text().replace("Run `python3 check.py`.", "Results must look right."))
    before = snapshot(root)
    assert "G3 item not met" in " ".join(prepare_build(root, "demo", relative).problems)
    result = run(root, "a\ns\n")
    assert "Choose one of: reject, skip, quit" in result.stdout
    assert snapshot(root) == before and not calls(home)


@pytest.mark.parametrize("state", ["done", "abandoned"])
def test_build_finished_prior_task_permits_new_request(build_env, state):
    root, _, home = build_env
    relative = request(build_env)
    path = root / relative
    path.rename(path.with_name("build-20261110T100000Z-first.md"))
    assert run(root, "a\n").exit_code == 0
    task_file = home / "tasks/demo-s001/task.json"
    task = json.loads(task_file.read_bytes())
    task["state"] = state
    task_file.write_text(json.dumps(task))
    relative = request(build_env, task_id="second-build")
    assert not prepare_build(root, "demo", relative).problems


@pytest.mark.parametrize(
    "damage", ["wrong-repo", "changed-request", "changed-contract", "missing-output"]
)
def test_build_recovery_checks_identity_and_retains_archive(build_env, monkeypatch, damage):
    root, _, home = build_env
    relative = request(build_env)
    original = project_proposals.finish_build

    def crash(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(project_proposals, "finish_build", crash)
    with pytest.raises(KeyboardInterrupt):
        apply_build(root, "demo", prepare_build(root, "demo", relative), "Researcher", "a")
    monkeypatch.setattr(project_proposals, "finish_build", original)
    (archive,) = (root / "projects/demo/runs").glob("*-build-S-001")
    if damage == "wrong-repo":
        task_file = home / "tasks/demo-s001/task.json"
        task_file.write_text(json.dumps({"repo": "/another/repo", "state": "running"}))
    elif damage == "changed-request":
        path = root / relative
        path.write_text(path.read_text().replace("Ready to build.", "Changed request."))
    elif damage == "changed-contract":
        (archive / "contract.json").write_text("{}\n")
    else:
        (archive / "chief-new.txt").unlink()
    before = snapshot(root)
    prepared = prepare_build(root, "demo", relative)
    if damage == "missing-output":
        assert prepared.recovered and not prepared.problems
        done = apply_build(root, "demo", prepared, "Other actor", "different approval")
        assert done.actor == "Researcher" and done.approval_text == "a"
        assert "chief new was not repeated" in (archive / "chief-new.txt").read_text()
    else:
        assert prepared.problems
        with pytest.raises(FormatError):
            apply_build(root, "demo", prepared, "Researcher", "a")
        assert snapshot(root) == before
    assert len(calls(home)) == 1


@pytest.mark.parametrize("contents", ["invalid json", "[]", "null"])
def test_build_unreadable_task_refuses_instead_of_guessing(build_env, contents):
    root, _, home = build_env
    relative = request(build_env)
    folder = home / "tasks/demo-s001"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(contents)
    before = snapshot(root)
    assert "Chief state not read" in " ".join(prepare_build(root, "demo", relative).problems)
    assert run(root).exit_code == 0 and snapshot(root) == before and not calls(home)


def test_build_occupied_task_directory_refuses(build_env):
    root, _, home = build_env
    relative = request(build_env)
    (home / "tasks/demo-s001").mkdir(parents=True)
    assert "without task.json" in " ".join(prepare_build(root, "demo", relative).problems)
    assert not calls(home)


@pytest.mark.parametrize(
    "config",
    [
        "budget = {rounds = 1, hours = -1}",
        'tool = "other"',
        'home = "relative"',
        'command = ""',
        "not toml",
    ],
)
def test_build_invalid_config_writes_nothing(build_env, config):
    root, _, home = build_env
    request(build_env)
    (root / "tools/chief.toml").write_text(config + "\n")
    before = snapshot(root)
    result = run(root)
    assert result.exit_code == 1 and "Error:" in result.output
    assert snapshot(root) == before and not calls(home)


def test_build_executable_start_failure_keeps_reason(build_env):
    root, _, home = build_env
    relative = request(build_env)
    path = root / "tools/chief.toml"
    text = path.read_text()
    line = next(line for line in text.splitlines() if line.startswith("command ="))
    path.write_text(text.replace(line, 'command = "/no/such/chief"'))
    result = run(root, "a\n")
    assert result.exit_code == 1
    done = outcome(root, relative)
    assert done.disposition == "failed" and "could not start" in done.reason
    assert not calls(home)


def test_build_draft_shell_fences_and_output_are_prefilled_correctly(build_env):
    root, _, _ = build_env
    path = root / SPEC
    doc = decode(path.read_bytes())
    doc.body = (
        "## Requirements\nBuild.\n\n## Acceptance criteria\n"
        "Run `python3 quick.py`.\n```bash\nset -e\npython3 full.py\n```\n"
        "Expected:\n```\nAll passed\n```\n"
    )
    path.write_bytes(encode(doc))
    result = CliRunner().invoke(
        app, ["draft", "build", "demo", "--root", str(root), "--spec", "S-001"]
    )
    assert result.exit_code == 0, result.output
    assert decode((root / result.stdout.strip()).read_bytes()).header["checks"] == [
        "python3 quick.py",
        "set -e\npython3 full.py",
    ]


@pytest.mark.parametrize(
    "mode,created",
    [("fail", False), ("fail-after-create", True), ("hang", False), ("hang-after-create", True)],
)
def test_build_reconciles_task_after_launcher_error(build_env, monkeypatch, mode, created):
    root, _, home = build_env
    relative = request(build_env)
    (home / mode).touch()
    if mode.startswith("hang"):
        monkeypatch.setattr(chief_adapter, "NEW_TIMEOUT", 1.0)
    before = snapshot(root)
    result = run(root, "a\n")
    assert result.exit_code == (0 if created else 1), result.output
    done = outcome(root, relative)
    assert done.disposition == ("applied" if created else "failed")
    assert done.result == ("chief task demo-s001" if created else None)
    (archive,) = (root / "projects/demo/runs").glob("*-build-S-001")
    text = (archive / "chief-new.txt").read_text()
    if created:
        assert "chief new reported an error, but the task exists" in result.stdout
        assert "Created chief task demo-s001" in text
        assert "task id demo-s001 is free" not in result.stdout
    else:
        assert "task id demo-s001 is free" in result.stdout
    if mode.startswith("hang"):
        assert "timed out" in text
    else:
        assert "exit status: 7" in text
    assert len(calls(home)) == 1
    assert run(root).stdout.strip() == "Nothing awaits your decision."
    for path, raw in before.items():
        assert (root / path).read_bytes() == raw


@pytest.mark.parametrize("created", [False, True])
def test_build_reconciles_task_after_oserror(build_env, monkeypatch, created):
    root, _, home = build_env
    relative = request(build_env)
    original = ChiefClient.new

    def error(self, *args, **kwargs):
        if created:
            original(self, *args, **kwargs)
        raise OSError("fixture launch error")

    monkeypatch.setattr(ChiefClient, "new", error)
    result = run(root, "a\n")
    assert result.exit_code == (0 if created else 1), result.output
    done = outcome(root, relative)
    assert done.disposition == ("applied" if created else "failed")
    (archive,) = (root / "projects/demo/runs").glob("*-build-S-001")
    assert "fixture launch error" in (archive / "chief-new.txt").read_text()
    if created:
        assert done.result == "chief task demo-s001"
        assert "chief new reported an error, but the task exists" in result.stdout
    else:
        assert "task id demo-s001 is free" in result.stdout


@pytest.mark.parametrize("task", [{"repo": "/different/repo"}, "malformed"])
def test_build_launcher_error_does_not_claim_unknown_or_mismatching_task(
    build_env, monkeypatch, task
):
    root, _, home = build_env
    relative = request(build_env)

    def error(*args, **kwargs):
        folder = home / "tasks/demo-s001"
        folder.mkdir(parents=True)
        (folder / "task.json").write_text(json.dumps(task) if isinstance(task, dict) else task)
        raise OSError("fixture launch error")

    monkeypatch.setattr(ChiefClient, "new", error)
    result = run(root, "a\n")
    assert result.exit_code == 1, result.output
    assert outcome(root, relative).disposition == "failed"
    assert "task id demo-s001 is free" not in result.stdout
    assert "chief new reported an error, but the task exists" not in result.stdout


def expected_output_spec(root, fence=""):
    path = root / SPEC
    document = decode(path.read_bytes())
    document.body = (
        "## Requirements\nBuild wordfreq.\n\n## Acceptance criteria\n"
        "`python3 wordfreq.py fixture.txt 3` prints exactly:\n"
        f"```{fence}\nthe 4\nfox 2\na 1\n```\n"
    )
    path.write_bytes(encode(document))


@pytest.mark.parametrize("fence", ["", "text"])
def test_build_draft_warns_about_exit_status_checks_when_spec_has_expected_output(build_env, fence):
    root, _, _ = build_env
    expected_output_spec(root, fence)
    result = CliRunner().invoke(
        app, ["draft", "build", "demo", "--root", str(root), "--spec", "S-001"]
    )
    assert result.exit_code == 0, result.output
    path = root / result.stdout.strip()
    text = path.read_text()
    example = 'test "$(python3 wordfreq.py fixture.txt 3)" = "$(printf \'the 4\\nfox 2\\na 1\')"'
    assert "# Checks pass on exit status only; the Spec shows expected output." in text
    assert example in text
    assert text.index("# Checks pass on exit status only") < text.index("\nchecks:")
    assert decode(path.read_bytes()).header["checks"] == ["python3 wordfreq.py fixture.txt 3"]
    filled = re.sub(r"## Why\n<fill:[^\n]*", "## Why\nBuild now.", text)
    assert validate_build_request(decode(filled.encode())).checks == (
        "python3 wordfreq.py fixture.txt 3",
    )


def test_build_preview_expected_output_note_is_advice_not_a_refusal(build_env):
    root, _, home = build_env
    expected_output_spec(root)
    relative = request(build_env, checks=["python3 wordfreq.py fixture.txt 3"])
    before = snapshot(root)
    result = run(root)
    assert result.exit_code == 0, result.output
    assert "Note: Checks pass on exit status only; the Spec shows expected output." in result.stdout
    assert 'test "$(python3 wordfreq.py fixture.txt 3)"' in result.stdout
    assert "Problem:" not in result.stdout
    assert not prepare_build(root, "demo", relative).problems
    assert snapshot(root) == before and not calls(home)


def test_build_contract_uses_current_successor_statement(build_env):
    root, _, home = build_env
    path = root / "projects/demo/claims/C-001.md"
    original = decode(path.read_bytes())
    successor = decode(path.read_bytes())
    successor.header.update(id="C-002", status="proposed")
    successor.body = "## Statement\nThe revised Claim is the current requirement.\n"
    (path.parent / "C-002.md").write_bytes(encode(successor))
    original.header.update(status="superseded", superseded_by="C-002", decisions=["D-001"])
    path.write_bytes(encode(original))
    relative = request(build_env)
    prepared = prepare_build(root, "demo", relative)
    assert not prepared.problems
    assert prepared.preview.build.gate.met
    goal = prepared.preview.build.contract["goal"]
    assert "## Target Claim C-001 (current: C-002): Statement\n" in goal
    assert sections(successor)["Statement"] in goal
    assert sections(original)["Statement"] not in goal
    before = snapshot(root)
    result = run(root)
    assert result.exit_code == 0, result.output
    assert "Target Claim C-001 (current: C-002): Statement" in result.stdout
    assert snapshot(root) == before and not calls(home)


@pytest.mark.parametrize("trust", [False, True])
def test_build_request_trust_is_previewed_and_reaches_argv_only_when_true(build_env, trust):
    root, _, home = build_env
    relative = request(build_env, trust=trust)
    result = run(root, "a\n")
    assert result.exit_code == 0, result.output
    assert (
        "Chief confirms the worker's folder-trust prompt: " + ("yes" if trust else "no")
    ) in result.stdout
    (call,) = calls(home)
    assert ("--trust" in call["argv"]) is trust
    assert "trust" not in call["contract"]  # Chief accepts this as a CLI option, not contract data.
    assert outcome(root, relative).result == "chief task demo-s001"


@pytest.mark.parametrize("trust", [False, True])
def test_build_draft_prefills_folder_trust_from_workspace_config(build_env, trust):
    root, _, home = build_env
    path = root / "tools/chief.toml"
    path.write_text(
        path.read_text().replace(
            'tool = "claude"', f'tool = "claude"\ntrust = {str(trust).lower()}'
        )
    )
    result = CliRunner().invoke(
        app, ["draft", "build", "demo", "--root", str(root), "--spec", "S-001"]
    )
    assert result.exit_code == 0, result.output
    document = decode((root / result.stdout.strip()).read_bytes())
    assert document.header["trust"] is trust and load_config(root).trust is trust
    # Config is a draft default: an older request without trust still means false.
    relative = request(build_env)
    assert not prepare_build(root, "demo", relative).preview.build.request.trust
    assert not calls(home)


@pytest.mark.parametrize("trust", ["true", 1, None])
def test_build_invalid_request_trust_is_refused_without_writes(build_env, trust):
    root, _, home = build_env
    relative = request(build_env, trust=trust)
    before = snapshot(root)
    prepared = prepare_build(root, "demo", relative)
    assert "trust: expected true or false" in " ".join(prepared.problems)
    with pytest.raises(FormatError):
        apply_build(root, "demo", prepared, "Researcher", "a")
    assert snapshot(root) == before and not calls(home)


def test_build_invalid_config_trust_is_refused_without_writes(build_env):
    root, _, home = build_env
    path = root / "tools/chief.toml"
    path.write_text(path.read_text().replace('tool = "claude"', 'tool = "claude"\ntrust = "true"'))
    request(build_env)
    before = snapshot(root)
    result = run(root)
    assert result.exit_code == 1 and "trust: expected true or false" in result.output
    assert snapshot(root) == before and not calls(home)
