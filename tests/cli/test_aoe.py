"""CLI protocol checks use fake sessions and temporary research projects only."""

import json
import shlex
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from toulmin.adapters.aoe import AoEError, AoESession
from toulmin.application.aoe import Binding, WorkspaceView
from toulmin.cli import aoe
from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.protocols.research_workspace import research_state

SESSION = "0123456789abcdef"


def invoke(root, *args):
    return CliRunner().invoke(app, ["aoe", *args, "--root", str(root)])


@pytest.fixture(autouse=True)
def no_real_aoe(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("A real AoE adapter must not be constructed in CLI tests")

    monkeypatch.setattr(aoe, "AoEClient", refuse)
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


@pytest.fixture
def fake_service(workbench, monkeypatch):
    binding = Binding(
        str(workbench),
        "demo",
        "saved-profile",
        "codex",
        SESSION,
        context="projects/demo/runs/context",
        token="fixture-token",
        delivery="submitted",
    )
    view = WorkspaceView(
        research_state(workbench, "demo"),
        binding,
        AoESession(SESSION, workbench, "codex", "live", "idle"),
        "submitted",
        ("Submitted to AoE; context-read receipt pending",),
        workbench / "context.md",
    )

    class Service:
        calls = []
        result = view
        failure = None
        client = None

        def __init__(self, root, project, client=None):
            self.client = client
            self.calls.append(("init", root, project, client))

        def outcome(self, call):
            self.calls.append(call)
            if self.failure:
                raise self.failure
            return self.result

        def open(self, agent="codex", *, new_session=False):
            return self.outcome(("open", agent, new_session))

        def bind(self, session_id=None, *, replace_existing=False):
            return self.outcome(("bind", session_id, replace_existing))

        def status(self, *, check_session=True):
            self.calls.append(("status", check_session))
            return self.result

        def refresh(self, *, resend=False):
            return self.outcome(("refresh", resend))

        def acknowledge(self, token):
            return self.outcome(("ack", token))

    monkeypatch.setattr(aoe, "AoEWorkspace", Service)
    return Service


def test_group_and_command_help_are_registered():
    runner = CliRunner()
    assert "aoe" in runner.invoke(app, ["--help"]).output
    result = runner.invoke(app, ["aoe", "--help"])
    assert result.exit_code == 0
    for name in ("open", "bind", "status", "refresh", "ack", "handoff"):
        assert name in result.output
        assert runner.invoke(app, ["aoe", name, "--help"]).exit_code == 0


def test_open_does_not_construct_client_or_attach_by_default(workbench, fake_service):
    result = invoke(workbench, "open", "demo")
    assert result.exit_code == 0, result.output
    assert ("init", workbench, "demo", None) in fake_service.calls
    assert ("open", "codex", False) in fake_service.calls
    assert "Submitted is not acknowledged" in result.output
    assert "context-read receipt pending" in result.output
    assert "BINDING\n" in result.output and "CONTEXT\n" in result.output


def test_explicit_profile_agent_and_new_session_are_forwarded(workbench, fake_service, monkeypatch):
    client = object()
    profiles = []

    def make_client(profile):
        profiles.append(profile)
        return client

    monkeypatch.setattr(aoe, "AoEClient", make_client)
    result = invoke(
        workbench, "open", "demo", "--profile", "trial", "--agent", "claude", "--new-session"
    )
    assert result.exit_code == 0, result.output
    assert profiles == ["trial"]
    assert ("init", workbench, "demo", client) in fake_service.calls
    assert ("open", "claude", True) in fake_service.calls


def test_attach_is_explicit_and_follows_printed_state(workbench, fake_service, monkeypatch):
    events = []
    original = aoe.typer.echo

    def echo(message=None, **kwargs):
        events.append(("output", str(message)))
        original(message, **kwargs)

    class Client:
        def __init__(self, profile):
            assert profile == "saved-profile"

        def attach(self, session_id):
            events.append(("attach", session_id))
            return 0

    monkeypatch.setattr(aoe.typer, "echo", echo)
    monkeypatch.setattr(aoe, "AoEClient", Client)
    result = invoke(workbench, "open", "demo", "--attach")
    assert result.exit_code == 0, result.output
    assert events[-1] == ("attach", SESSION)
    assert any(event[0] == "output" and "PROJECT" in event[1] for event in events[:-1])


def test_attach_refuses_an_unverified_or_nonlive_session(workbench, fake_service):
    fake_service.result = replace(fake_service.result, session=None)
    result = invoke(workbench, "open", "demo", "--attach")
    assert result.exit_code == 1
    assert "Cannot attach" in result.output


def test_bind_current_and_replace_prepare_context_without_send(workbench, fake_service):
    result = invoke(workbench, "bind", "demo")
    assert result.exit_code == 0, result.output
    assert ("bind", None, False) in fake_service.calls
    assert "no message was sent" in result.output
    assert "Read context:" in result.output
    assert "run its context-read receipt command" in result.output
    result = invoke(workbench, "bind", "demo", "--session", SESSION, "--replace")
    assert result.exit_code == 0, result.output
    assert ("bind", SESSION, True) in fake_service.calls


def test_refresh_does_not_implicitly_resend(workbench, fake_service):
    assert invoke(workbench, "refresh", "demo").exit_code == 0
    assert ("refresh", False) in fake_service.calls
    assert invoke(workbench, "refresh", "demo", "--resend").exit_code == 0
    assert ("refresh", True) in fake_service.calls


def test_unready_delivery_shows_shell_quoted_profile_and_refresh_commands(
    workbench, fake_service, monkeypatch
):
    monkeypatch.setenv("TOULMIN_AOE_COMMAND", "/tmp/aoe binary;literal")
    binding = replace(fake_service.result.binding, delivery="prepared")
    fake_service.result = replace(fake_service.result, binding=binding, context_status="prepared")
    result = invoke(workbench, "refresh", "demo")
    assert result.exit_code == 0, result.output
    assert shlex.join(["/tmp/aoe binary;literal", "-p", "saved-profile"]) in result.output
    assert (
        shlex.join(
            [
                "toulmin",
                "aoe",
                "refresh",
                "demo",
                "--root",
                str(workbench),
                "--profile",
                "saved-profile",
            ]
        )
        in result.output
    )
    assert "add --resend only to explicitly retry" in result.output


def test_online_failure_is_friendly_and_recovery_uses_recorded_profile(workbench, fake_service):
    fake_service.failure = AoEError("Native startup is unresolved")
    result = invoke(workbench, "open", "demo")
    assert result.exit_code == 1
    assert "Error: Native startup is unresolved" in result.output
    assert "saved-profile" in result.output
    assert "Traceback" not in result.output


def test_ack_is_receipt_only_and_needs_no_adapter(workbench, fake_service):
    result = invoke(workbench, "ack", "demo", "--token", "fixture-token")
    assert result.exit_code == 0, result.output
    assert ("ack", "fixture-token") in fake_service.calls
    assert "not research approval" in result.output


def test_json_serializes_paths_and_offline_disables_session_check(workbench, fake_service):
    result = invoke(workbench, "status", "demo", "--offline", "--json", "--profile", "uninstalled")
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value["context_path"] == str(workbench / "context.md")
    assert value["session"]["path"] == str(workbench)
    assert ("status", False) in fake_service.calls


def test_real_offline_status_works_without_aoe(workbench):
    result = invoke(workbench, "status", "demo", "--offline", "--json")
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value["context_status"] == "unbound"
    assert value["research"]["project"] == "demo"
    assert value["binding"] is None


def test_real_offline_status_reports_invalid_research_as_nonzero(workbench):
    (workbench / "projects/demo/brief.md").write_text("[[C-999]]\n")
    result = invoke(workbench, "status", "demo", "--offline", "--json")
    assert result.exit_code == 1
    assert json.loads(result.output)["research"]["errors"]


def test_handoff_draft_and_explicit_confirmed_apply_keep_protocol_semantics(workbench, monkeypatch):
    drafted = invoke(workbench, "handoff", "demo")
    assert drafted.exit_code == 0, drafted.output
    path = drafted.output.strip()
    charter = workbench / "projects/demo/PROJECT.md"
    before = charter.read_bytes()
    assert invoke(workbench, "handoff", "demo", "--apply", path, "--confirm").exit_code == 2
    monkeypatch.setenv("TOULMIN_ACTOR", "Fixture Researcher")
    refused = invoke(workbench, "handoff", "demo", "--apply", path)
    assert refused.exit_code == 1 and "explicit researcher confirmation" in refused.output
    assert charter.read_bytes() == before
    applied = invoke(workbench, "handoff", "demo", "--apply", path, "--confirm")
    assert applied.exit_code == 0, applied.output
    assert (
        decode((workbench / applied.output.strip()).read_bytes()).header["applied_by"]
        == "Fixture Researcher"
    )
    replay = invoke(workbench, "handoff", "demo", "--apply", path, "--confirm")
    assert replay.exit_code == 0 and replay.output == applied.output
    assert decode(charter.read_bytes()).header["stage"] == "explore"


@pytest.mark.parametrize(
    "args",
    [("--input", "summary.md", "--apply", "draft.md"), ("--confirm",), ("--confirmed-by", "Human")],
)
def test_handoff_rejects_ambiguous_or_inapplicable_confirmation(workbench, args):
    result = invoke(workbench, "handoff", "demo", *args)
    assert result.exit_code == 2


def test_handoff_explicit_actor_overrides_environment(workbench, monkeypatch):
    drafted = invoke(workbench, "handoff", "demo")
    monkeypatch.setenv("TOULMIN_ACTOR", "Environment Actor")
    result = invoke(
        workbench,
        "handoff",
        "demo",
        "--apply",
        drafted.output.strip(),
        "--confirmed-by",
        "Explicit Researcher",
        "--confirm",
    )
    assert result.exit_code == 0, result.output
    assert (
        decode((workbench / result.output.strip()).read_bytes()).header["applied_by"]
        == "Explicit Researcher"
    )


def test_invalid_agent_is_rejected_before_service_work(workbench, fake_service):
    result = invoke(workbench, "open", "demo", "--agent", "unsupported")
    assert result.exit_code == 2
    assert fake_service.calls == []
