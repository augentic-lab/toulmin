"""AoE interface checks use fake subprocesses, never real provider sessions."""

import json
import subprocess
from pathlib import Path

import pytest

from toulmin.adapters import aoe
from toulmin.adapters.aoe import AoEClient, AoEError

SID = "0123456789abcdef"
OTHER = "fedcba9876543210"


def row(**changes):
    return {
        "id": SID,
        "path": "/work/research space",
        "tool": "codex",
        "state": "live",
        "status": "idle",
        "title": "Toulmin: trial",
        **changes,
    }


@pytest.fixture
def calls(monkeypatch):
    recorded = []
    responses = []

    def run(argv, **kwargs):
        recorded.append((argv, kwargs))
        assert responses, f"Unexpected call: {argv}"
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, subprocess.CompletedProcess):
            return response
        return subprocess.CompletedProcess(argv, 0, response, "")

    monkeypatch.setattr(aoe.subprocess, "run", run)
    monkeypatch.setattr(aoe.shutil, "which", lambda command: str(command))
    monkeypatch.setattr(aoe.time, "sleep", lambda _: None)
    return recorded, responses


def client():
    return AoEClient(profile="trial-1", command="/tools/aoe with spaces")


def test_list_show_current_and_optional_fields(calls):
    recorded, responses = calls
    responses.extend(
        [
            "[]",
            json.dumps([row(status=None)]),
            json.dumps(row(agent_session_id="provider-123")),
            json.dumps(row()),
        ]
    )
    adapter = client()
    assert adapter.list_sessions() == ()
    assert adapter.list_sessions()[0].status is None
    session = adapter.show(SID)
    assert session.path == Path("/work/research space")
    assert session.agent_session_id == "provider-123"
    assert adapter.current().title == "Toulmin: trial"
    assert recorded[0][0] == ["/tools/aoe with spaces", "-p", "trial-1", "list", "--json"]
    assert recorded[2][0][-4:] == ["session", "show", SID, "--json"]
    assert recorded[3][0][-3:] == ["session", "current", "--json"]
    for _, kwargs in recorded:
        assert 0 < kwargs["timeout"] <= 45
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "shell" not in kwargs


@pytest.mark.parametrize("profile", ["", "../bad", "-main", "a/b", "a b", "x\n", "a" * 65])
def test_invalid_profiles_do_not_invoke_cli(calls, profile):
    with pytest.raises(AoEError, match="profile"):
        AoEClient(profile, "/tools/aoe")
    assert calls[0] == []


@pytest.mark.parametrize("session_id", ["", "trial", "0123456789ABCDEF", SID + "0", "../bad"])
def test_invalid_id_never_reaches_cli(calls, session_id):
    adapter = client()
    for operation in (
        lambda: adapter.show(session_id),
        lambda: adapter.send(session_id, "message"),
        lambda: adapter.ready(session_id),
        lambda: adapter.attach(session_id),
    ):
        with pytest.raises(AoEError, match="session ID"):
            operation()
    assert calls[0] == []


@pytest.mark.parametrize(
    "value",
    [
        {},
        None,
        [None],
        [row(path="relative")],
        [row(id="title")],
        [row(tool=3)],
        [row(state="")],
        [row(status=False)],
        [row(agent_session_id=[])],
        [row(title=None)],
        [row(), row()],
        [row(), row(path=None)],
    ],
)
def test_malformed_list_fails_instead_of_skipping_entries(calls, value):
    calls[1].append(json.dumps(value))
    with pytest.raises(AoEError):
        client().list_sessions()


@pytest.mark.parametrize("output", ["not json", "[", '{"id": null}', "[]"])
def test_malformed_show(calls, output):
    calls[1].append(output)
    with pytest.raises(AoEError, match="Malformed"):
        client().show(SID)


def test_show_rejects_different_session(calls):
    calls[1].append(json.dumps(row(id=OTHER)))
    with pytest.raises(AoEError, match="different session"):
        client().show(SID)


@pytest.mark.parametrize("profile", ["other", "", None, 1, ["trial-1"]])
@pytest.mark.parametrize("operation", ["show", "current", "list_sessions"])
def test_response_profile_mismatch_or_malformed_profile_is_rejected(calls, profile, operation):
    value = row(profile=profile)
    calls[1].append(json.dumps([value] if operation == "list_sessions" else value))
    adapter = client()
    with pytest.raises(AoEError, match="profile"):
        getattr(adapter, operation)(*([SID] if operation == "show" else []))


def test_matching_response_profile_is_accepted(calls):
    calls[1].append(json.dumps(row(profile="trial-1")))
    assert client().show(SID).id == SID


def test_create_uses_native_flags_without_trust_or_config_changes(calls, tmp_path):
    root = tmp_path / "work bench"
    root.mkdir()
    calls[1].extend([f"Added session: Toulmin: trial ({SID})\n", json.dumps(row(path=str(root)))])
    assert client().create(root, "trial", "codex").id == SID
    argv, kwargs = calls[0][0]
    assert argv == [
        "/tools/aoe with spaces",
        "-p",
        "trial-1",
        "add",
        str(root),
        "-t",
        "Toulmin: trial",
        "-g",
        "research/trial",
        "--tool",
        "codex",
        "--launch",
    ]
    assert kwargs["timeout"] == 45


@pytest.mark.parametrize("project,agent", [("../bad", "codex"), ("trial", "bash")])
def test_create_rejects_invalid_inputs_before_mutation(calls, tmp_path, project, agent):
    with pytest.raises(AoEError):
        client().create(tmp_path, project, agent)
    assert calls[0] == []


def test_create_retains_id_if_followup_show_fails(calls, tmp_path):
    calls[1].extend([f"Session added: {SID}\n", "not JSON"])
    with pytest.raises(AoEError) as caught:
        client().create(tmp_path, "trial", "claude")
    assert caught.value.session_id == SID
    assert caught.value.creation_uncertain
    assert SID in str(caught.value)


@pytest.mark.parametrize("output", ["Added session", SID + "0", f"{SID} {OTHER}"])
def test_create_ambiguous_response_requires_reconciliation(calls, tmp_path, output):
    calls[1].append(output)
    with pytest.raises(AoEError) as caught:
        client().create(tmp_path, "trial", "codex")
    assert caught.value.creation_uncertain
    assert caught.value.session_id is None
    assert len(calls[0]) == 1


def test_create_timeout_does_not_claim_absence_or_retry(calls, tmp_path):
    calls[1].append(subprocess.TimeoutExpired("aoe", 45))
    with pytest.raises(AoEError, match="outcome is unknown") as caught:
        client().create(tmp_path, "trial", "codex")
    assert caught.value.creation_uncertain
    assert len(calls[0]) == 1


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired("aoe", 45, output=f"Created {SID}".encode()),
        subprocess.CompletedProcess([], 1, f"Created {SID}", "launch failed"),
    ],
)
def test_create_partial_command_failure_retains_reported_id(calls, tmp_path, failure):
    calls[1].append(failure)
    with pytest.raises(AoEError) as caught:
        client().create(tmp_path, "trial", "codex")
    assert caught.value.session_id == SID
    assert caught.value.creation_uncertain
    assert len(calls[0]) == 1


@pytest.mark.parametrize(
    "error",
    [OSError("unavailable"), UnicodeError("invalid bytes"), subprocess.TimeoutExpired("aoe", 15)],
)
def test_subprocess_failures_are_domain_errors(calls, error):
    calls[1].append(error)
    with pytest.raises(AoEError):
        client().list_sessions()


def test_command_failure_contains_bounded_diagnostic(calls):
    calls[1].append(subprocess.CompletedProcess([], 2, "", "x" * 5000 + " failed"))
    with pytest.raises(AoEError, match=r"failed \(2\)") as caught:
        client().show(SID)
    assert str(caught.value).endswith(" failed")
    assert len(str(caught.value)) < 1600


def test_send_never_revives_or_retries_and_keeps_text_literal(calls):
    calls[1].append("")
    message = "--literal\n$(do not run); `nothing`"
    client().send(SID, message)
    assert calls[0][0][0][-5:] == ["send", "--no-revive", SID, "--", message]
    assert len(calls[0]) == 1


@pytest.mark.parametrize("message", ["", "  ", "hi\x00bad"])
def test_send_invalid_message_does_not_invoke_cli(calls, message):
    with pytest.raises(AoEError, match="message"):
        client().send(SID, message)
    assert calls[0] == []


@pytest.mark.parametrize(
    "state,status",
    [
        ("archived", "idle"),
        ("trashed", "waiting"),
        ("live", "starting"),
        ("live", "running"),
        ("live", None),
    ],
)
def test_ready_requires_live_idle_status_even_if_prompt_could_be_visible(calls, state, status):
    calls[1].append(json.dumps(row(state=state, status=status)))
    ready, reason = client().ready(SID)
    assert not ready
    assert reason
    assert len(calls[0]) == 1


@pytest.mark.parametrize(
    "screen",
    [
        "",
        "No prompt",
        "› \nDo you trust this directory?",
        "› \nUpdate available",
        "› \nWorking… (esc to interrupt)",
        "› \nPermission required",
        "› \nWould you like to proceed?",
        "› \nSelect an option",
        "› \nSign in",
        "› 1. Yes\n  2. No",
        "› Yes\n  No",
        "› \nThinking (2s)",
    ],
)
def test_ready_refuses_empty_busy_permission_trust_update_or_menu(calls, screen):
    calls[1].extend([json.dumps(row()), screen])
    assert client().ready(SID)[0] is False
    assert len(calls[0]) == 2


@pytest.mark.parametrize(
    "tool,status,prompt",
    [
        ("codex", "idle", "OpenAI Codex\n› \n? for shortcuts"),
        ("claude", "waiting", "Claude Code\n❯ \n? for shortcuts"),
        ("claude", "idle", "Claude Code\n> \n"),
        ("codex", "idle", "› Earlier submitted message\nReply\n› Ask Codex to do anything\n"),
        ("claude", "idle", "❯ Earlier submitted message\nReply\n❯ \n"),
        (
            "claude",
            "waiting",
            'Claude Code\n───\n❯ Try "fix typecheck errors"\n───\n  ? for shortcuts',
        ),
    ],
)
def test_ready_requires_two_matching_quiet_captures(calls, tool, status, prompt):
    value = json.dumps(row(tool=tool, status=status))
    calls[1].extend([value, prompt, value, prompt])
    ready, reason = client().ready(SID)
    assert ready
    assert "two" in reason
    assert [args[3:5] for args, _ in calls[0]] == [
        ["session", "show"],
        ["session", "capture"],
        ["session", "show"],
        ["session", "capture"],
    ]


def test_ready_fails_when_screen_or_status_changes(calls):
    value = json.dumps(row())
    calls[1].extend([value, "› ", value, "› Ask Codex to do anything"])
    assert client().ready(SID)[0] is False
    calls[1].extend([value, "› ", json.dumps(row(status="starting"))])
    assert client().ready(SID)[0] is False


@pytest.mark.parametrize(
    "tool,prompt",
    [
        ("codex", "› unfinished researcher draft"),
        ("claude", "❯ unfinished researcher draft"),
        ("claude", "> unfinished researcher draft"),
        ("codex", "› \nPrior response\n› unfinished researcher draft"),
        ("codex", "› Ask Codex to do anything else"),
        ("claude", '❯ Try "fix typecheck errors" and then commit'),
        ("codex", '› Try "fix typecheck errors"'),
    ],
)
def test_ready_refuses_occupied_native_input(calls, tool, prompt):
    calls[1].extend([json.dumps(row(tool=tool)), prompt])
    ready, reason = client().ready(SID)
    assert not ready
    assert "contains text" in reason
    assert len(calls[0]) == 2


# Shape of the WI8 live Codex screen after a completed turn: the reply quotes
# "approve"/"approval", which once blocked every later refresh.
FINISHED_TURN = (
    "• Verified: the receipt does not approve research.\n"
    "  No research approval implied; permission settings unchanged.\n"
    "  Conclusion: waiting for the researcher.\n"
    "  Decision needed: How would you like to proceed?\n\n"
    "  Worked for 18s • 17:49\n\n\n"
    "› Ask Codex to do anything\n\n"
    "  GPT medium · /tmp/workbench · Context 5% used\n"
    "  ? for shortcuts\n"
)


def test_ready_ignores_blocking_words_in_the_agents_earlier_reply(calls):
    value = json.dumps(row(status="waiting"))
    calls[1].extend([value, FINISHED_TURN, value, FINISHED_TURN])
    ready, reason = client().ready(SID)
    assert ready, reason


@pytest.mark.parametrize(
    "tool,screen",
    [
        (
            "codex",
            "Reply\n\n• Working (5s • esc to interrupt)\n\n› Ask Codex to do anything\n  ? x",
        ),
        ("codex", "Reply\nThinking\n› \n"),
        ("codex", "Earlier text\nWould you like to make these changes?\n› \n"),
        ("claude", "Reply\n✻ Thinking… (esc to interrupt)\n\n────\n❯ \n────\n  ? for shortcuts"),
    ],
)
def test_ready_refuses_busy_state_next_to_the_input_line(calls, tool, screen):
    calls[1].extend([json.dumps(row(tool=tool)), screen])
    ready, reason = client().ready(SID)
    assert not ready
    assert "busy state" in reason


# Raw WI8 live Claude composer: the suggested prompt is dim, the glyph is not.
SUGGESTED = (
    "Reply\n\x1b[39m\u276f\u00a0\x1b[2mgo with 4, draft the proposal\x1b[0m\x1b[39m\x1b[49m\n"
)


def test_ready_treats_dim_composer_text_as_a_hint(calls):
    value = json.dumps(row(tool="claude", status="waiting"))
    calls[1].extend([value, SUGGESTED, value, SUGGESTED])
    ready, reason = client().ready(SID)
    assert ready, reason
    assert all("--strip-ansi" not in args for args, _ in calls[0])


@pytest.mark.parametrize(
    "screen",
    [
        "Reply\n\x1b[39m\u276f \x1b[22mtyped by the researcher\x1b[0m\n",
        "Reply\n\u276f \x1b[2mhint\x1b[0m typed after the hint\n",
        "Reply\n\u276f \x1b[38;5;2mgreen typed text\x1b[0m\n",
        "Reply\n\u276f \x1b[38;2;2;2;2mrgb typed text\x1b[0m\n",
    ],
)
def test_ready_refuses_visible_composer_text_in_raw_capture(calls, screen):
    calls[1].extend([json.dumps(row(tool="claude")), screen])
    ready, reason = client().ready(SID)
    assert not ready
    assert "contains text" in reason


def test_ready_handles_unavailable_capture_conservatively(calls):
    calls[1].extend([json.dumps(row()), OSError("pane missing")])
    ready, reason = client().ready(SID)
    assert not ready
    assert "unavailable" in reason


def test_attach_inherits_terminal_without_timeout(calls):
    calls[1].append(subprocess.CompletedProcess([], 7))
    assert client().attach(SID) == 7
    argv, kwargs = calls[0][0]
    assert argv[-3:] == ["session", "attach", SID]
    assert kwargs == {"check": False}


def test_resolution_explicit_then_env_then_local_then_path(monkeypatch, tmp_path, calls):
    monkeypatch.setenv("TOULMIN_AOE_COMMAND", "/env/aoe")
    assert AoEClient(command="/explicit/aoe").command == "/explicit/aoe"
    assert AoEClient().command == "/env/aoe"
    monkeypatch.delenv("TOULMIN_AOE_COMMAND")
    monkeypatch.setattr(aoe.Path, "home", lambda: tmp_path)
    local = tmp_path / ".local/bin/aoe"
    local.parent.mkdir(parents=True)
    local.write_text("unused")
    local.chmod(0o755)
    assert AoEClient().command == str(local)
    local.unlink()
    calls[1].append("Agent of Empires (aoe)")
    assert AoEClient().command == "aoe"
    calls[1].append("An unrelated audio package")
    with pytest.raises(AoEError, match="not Agent of Empires"):
        AoEClient()


def test_missing_executable_is_clear(monkeypatch, calls):
    monkeypatch.setattr(aoe.shutil, "which", lambda _: None)
    with pytest.raises(AoEError, match="not found"):
        client()
    assert calls[0] == []
