"""Native CLI continuation is explicit, scoped to exploration and archived per turn."""

import json
import sys
from dataclasses import replace

import pytest

from toulmin.adapters.base import Session
from toulmin.adapters.claude_code import ClaudeCode
from toulmin.adapters.codex import LAST_MESSAGE, Codex


@pytest.fixture
def native_cli(tmp_path):
    program = tmp_path / "native"
    program.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "root = pathlib.Path(os.environ['FAKE_ROOT'])\n"
        "codex = args[0] == 'exec'\n"
        "resume = 'resume' if codex else '--resume'\n"
        "resumed = resume in args\n"
        "identity = 'native-thread-001'\n"
        "prompt = sys.stdin.buffer.read().decode('utf-8')\n"
        "with (root / 'calls.jsonl').open('a') as log:\n"
        "    log.write(json.dumps({'args': args, 'prompt': prompt, "
        "'cwd': str(pathlib.Path.cwd())}) + '\\n')\n"
        "if resumed:\n"
        "    assert args[args.index(resume) + 1] == identity\n"
        "    assert (root / 'saved').read_text() == identity\n"
        "    assert (pathlib.Path.cwd() / 'download.txt').is_file()\n"
        "    if codex:\n"
        "        assert args[-3:] == ['resume', identity, '-']\n"
        "if os.environ.get('FAKE_MODE') == 'fail':\n"
        "    print('native session not found', file=sys.stderr)\n"
        "    sys.exit(7)\n"
        "(root / 'saved').write_text(identity)\n"
        "(pathlib.Path.cwd() / 'download.txt').write_text(prompt)\n"
        "if os.environ.get('FAKE_MODE') == 'missing': identity = None\n"
        "if os.environ.get('FAKE_MODE') == 'different': identity = 'other-thread'\n"
        "if codex:\n"
        "    pathlib.Path(args[args.index('-o') + 1]).write_text('Answer: ' + prompt)\n"
        "    print(json.dumps({'type': 'thread.started', 'thread_id': identity}))\n"
        "else:\n"
        "    print(json.dumps({'type': 'result', 'result': 'Answer: ' + prompt, "
        "'session_id': identity}))\n"
    )
    program.chmod(0o755)
    return program


def persistent_session(tmp_path, native_cli, *, resume_id=None, mode="", turn=1):
    workspace = tmp_path / "research"
    workspace.mkdir(exist_ok=True)
    archive = tmp_path / f"request-{turn}"
    archive.mkdir()
    return Session(
        prompt=f"Exact input {turn}\n中文\r\n",
        model="configured-model",
        timeout_seconds=5,
        command=str(native_cli),
        env=(("FAKE_ROOT", str(tmp_path)), ("FAKE_MODE", mode)),
        workspace=workspace,
        resume_id=resume_id,
        persistent=True,
        archive_directory=archive,
    )


@pytest.mark.parametrize("adapter", [ClaudeCode(), Codex()], ids=["claude", "codex"])
def test_persistent_calls_resume_exact_id_and_keep_separate_archives(tmp_path, native_cli, adapter):
    first = persistent_session(tmp_path, native_cli)
    one = adapter.run(first)
    assert one.failure is None
    assert one.session_id == "native-thread-001"
    assert first.archive_directory is not None
    archived = {path.name: path.read_bytes() for path in first.archive_directory.iterdir()}
    second = persistent_session(tmp_path, native_cli, resume_id=one.session_id, turn=2)
    two = adapter.run(second)
    assert two.failure is None
    assert two.session_id == one.session_id
    assert {path.name: path.read_bytes() for path in first.archive_directory.iterdir()} == archived
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == 2
    for session, call in zip((first, second), calls, strict=True):
        assert call["prompt"] == session.prompt
        assert call["cwd"] == str(session.workspace)
        assert session.archive_directory is not None
        assert one.session_id in (session.archive_directory / "tool-events.jsonl").read_text()
        assert (session.archive_directory / "tool-stderr.log").read_bytes() == b""
        args = call["args"]
        if isinstance(adapter, ClaudeCode):
            assert "--no-session-persistence" not in args
            assert "--safe-mode" in args and "--restricted" in args
            assert args[args.index("--tools") + 1] == "Bash,WebSearch,WebFetch"
            assert args[args.index("--permission-mode") + 1] == "dontAsk"
            assert args[args.index("--permission-prompts") + 1] == "none"
            settings = json.loads(args[args.index("--settings") + 1])
            assert settings["sandbox"]["failIfUnavailable"]
            assert not settings["sandbox"]["allowUnsandboxedCommands"]
        else:
            assert "--ephemeral" not in args
            assert args[args.index("--sandbox") + 1] == "workspace-write"
            assert args[args.index("-C") + 1] == str(session.workspace)
            assert 'sandbox_mode="workspace-write"' in args
            assert 'approval_policy="never"' in args
            assert 'web_search="live"' in args
            assert "sandbox_workspace_write.network_access=true" in args
            assert "sandbox_workspace_write.writable_roots=[]" in args
            assert "sandbox_workspace_write.exclude_slash_tmp=true" in args
            assert "sandbox_workspace_write.exclude_tmpdir_env_var=true" in args
            assert "--ignore-user-config" in args and "--ignore-rules" in args
            assert "project_doc_max_bytes=0" in args and "features.hooks=false" in args
            assert args[args.index("-o") + 1] == str(session.archive_directory / LAST_MESSAGE)
            assert (session.archive_directory / LAST_MESSAGE).read_bytes() == (
                "Answer: " + session.prompt
            ).encode()
    assert "--resume" not in calls[0]["args"] and "resume" not in calls[0]["args"]
    assert not (tmp_path / "tool-events.jsonl").exists()
    assert not (tmp_path / "research" / "tool-events.jsonl").exists()


@pytest.mark.parametrize("adapter", [ClaudeCode(), Codex()], ids=["claude", "codex"])
@pytest.mark.parametrize("mode", ["different", "fail"])
def test_native_resume_failures_are_explicit_and_never_retry(tmp_path, native_cli, adapter, mode):
    first = persistent_session(tmp_path, native_cli)
    original = adapter.run(first)
    resumed = persistent_session(
        tmp_path, native_cli, resume_id=original.session_id, mode=mode, turn=2
    )
    outcome = adapter.run(resumed)
    assert outcome.failure is not None
    assert (
        "continuity was not established" in outcome.failure
        if mode != "fail"
        else ("exit status 7" in outcome.failure)
    )
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 2
    assert resumed.archive_directory is not None
    assert (resumed.archive_directory / "tool-events.jsonl").exists()
    if mode != "fail":
        assert outcome.text == "Answer: " + resumed.prompt


@pytest.mark.parametrize("adapter", [ClaudeCode(), Codex()], ids=["claude", "codex"])
@pytest.mark.parametrize("resumed", [False, True])
def test_missing_native_identifier_preserves_useful_answer(tmp_path, native_cli, adapter, resumed):
    if resumed:
        adapter.run(persistent_session(tmp_path, native_cli, turn=0))
    session = persistent_session(
        tmp_path, native_cli, mode="missing", resume_id="native-thread-001" if resumed else None
    )
    outcome = adapter.run(session)
    assert outcome.failure is None
    assert outcome.session_id is None
    assert outcome.text == "Answer: " + session.prompt


@pytest.mark.parametrize(
    "resume_id", ["", "--last", "-r", "../native", "a/b", "a b", "a\n", "x" * 129]
)
def test_resume_identifier_cannot_change_flags_or_select_transcripts(
    tmp_path, native_cli, resume_id
):
    with pytest.raises(ValueError, match="safe native session identifier"):
        persistent_session(tmp_path, native_cli, resume_id=resume_id)
    assert not (tmp_path / "calls.jsonl").exists()


def test_persistence_requires_exploration_and_distinct_archive(tmp_path):
    base = Session("prompt", "", 5, "unused")
    with pytest.raises(ValueError, match="persistent exploration requires"):
        replace(base, persistent=True)
    with pytest.raises(ValueError, match="persistent exploration requires"):
        replace(base, persistent=True, workspace=tmp_path)
    with pytest.raises(ValueError, match="resume_id requires"):
        replace(base, resume_id="native-thread")
    with pytest.raises(ValueError, match="outside"):
        replace(base, persistent=True, workspace=tmp_path, archive_directory=tmp_path / "logs")


def test_codex_refuses_existing_last_message_before_call(tmp_path, native_cli):
    session = persistent_session(tmp_path, native_cli)
    assert session.archive_directory is not None
    target = tmp_path / "original"
    target.write_text("preserve")
    (session.archive_directory / LAST_MESSAGE).symlink_to(target)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        Codex().run(session)
    assert target.read_text() == "preserve"
    assert not (tmp_path / "calls.jsonl").exists()
