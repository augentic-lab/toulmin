"""Binding, context, confirmation and retry boundaries without live agents."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession
from toulmin.application.aoe import AoEWorkspace
from toulmin.cli.initialize import initialize
from toulmin.core.documents import FormatError

SID = "a" * 16


class FakeAoE(AoEClient):
    def __init__(self, root: Path, profile: str = "main"):
        self.profile = profile
        self.root = root
        self.sessions = {}
        self.created = 0
        self.sent = []
        self.is_ready = True
        self.create_error = None
        self.send_error = False
        self.on_send = None

    def list_sessions(self):
        return tuple(self.sessions.values())

    def show(self, session_id):
        if session_id not in self.sessions:
            raise AoEError("No such session")
        return self.sessions[session_id]

    def current(self):
        return next(iter(self.sessions.values()))

    def add_session(self, project="demo", session_id=SID):
        session = AoESession(
            session_id, self.root, "codex", "live", "idle", "native-a", f"Toulmin: {project}"
        )
        self.sessions[session_id] = session
        return session

    def create(self, root, project, agent):
        self.created += 1
        session = self.add_session(project, f"{self.created:016x}")
        self.sessions[session.id] = replace(session, tool=agent)
        if self.create_error == "unknown":
            raise AoEError("timeout", creation_uncertain=True)
        if self.create_error == "identified":
            raise AoEError("show timed out", session_id=session.id, creation_uncertain=True)
        if self.create_error == "absent":
            del self.sessions[session.id]
            raise AoEError("timeout", creation_uncertain=True)
        return self.sessions[session.id]

    def ready(self, session_id):
        return self.is_ready, "idle" if self.is_ready else "starting; open AoE and refresh"

    def send(self, session_id, message):
        self.sent.append((session_id, message))
        if self.on_send:
            self.on_send()
        if self.send_error:
            raise AoEError("send timed out; delivery unknown")


@pytest.fixture
def fake(workbench):
    return FakeAoE(workbench)


def workspace(root, client):
    return AoEWorkspace(root, "demo", client)


def stored(root):
    return json.loads((root / "projects/demo/.aoe/binding.json").read_text())


def test_open_reuses_session_and_submission_is_not_read_receipt(workbench, fake):
    app = workspace(workbench, fake)
    first = app.open()
    assert first.context_status == "submitted"
    assert first.binding and first.context_path and first.context_path.is_file()
    assert "ACTIONS" in first.context_path.with_name("state.md").read_text()
    app.open()
    app.refresh()
    assert fake.created == 1 and len(fake.sent) == 1
    receipt = app.acknowledge(first.binding.token)
    assert receipt.context_status == "acknowledged"
    app.open()
    assert len(fake.sent) == 1
    assert list((workbench / "projects/demo/claims").glob("C-*.md")) == []


def test_busy_bind_prepares_context_without_sending_or_creating(workbench, fake):
    fake.add_session()
    fake.is_ready = False
    app = workspace(workbench, fake)
    view = app.bind()
    assert view.context_status == "prepared" and not fake.sent and fake.created == 0
    app.refresh()
    assert not fake.sent
    fake.is_ready = True
    assert app.refresh().context_status == "submitted"
    assert len(fake.sent) == 1


@pytest.mark.parametrize("failure", ["unknown", "identified"])
def test_create_failure_preserves_intent_and_recovers_without_duplication(workbench, fake, failure):
    app = workspace(workbench, fake)
    fake.create_error = failure
    with pytest.raises(AoEError):
        app.open()
    assert stored(workbench)["known_ids"] == []
    view = app.open()
    assert view.binding.session_id in fake.sessions
    assert fake.created == 1 and len(fake.sent) == 1


def test_unknown_creation_never_blindly_retries(workbench, fake):
    fake.create_error = "absent"
    app = workspace(workbench, fake)
    with pytest.raises(AoEError):
        app.open()
    with pytest.raises(FormatError, match="unresolved"):
        app.open()
    assert fake.created == 1
    fake.add_session()
    app.bind(SID, replace_existing=True)
    assert stored(workbench)["session_id"] == SID


def test_uncertain_send_requires_explicit_resend(workbench, fake):
    fake.send_error = True
    app = workspace(workbench, fake)
    assert app.open().context_status == "uncertain"
    app.open()
    app.refresh()
    assert len(fake.sent) == 1
    fake.send_error = False
    assert app.refresh(resend=True).context_status == "submitted"
    assert len(fake.sent) == 2


def test_agent_can_ack_while_send_is_in_flight(workbench, fake):
    app = workspace(workbench, fake)
    fake.on_send = lambda: app.acknowledge(stored(workbench)["token"])
    assert app.open().context_status == "acknowledged"
    assert stored(workbench)["delivery"] == "acknowledged"


def test_external_research_edit_requires_new_snapshot_and_rejects_old_ack(workbench, fake):
    app = workspace(workbench, fake)
    original = app.open()
    app.acknowledge(original.binding.token)
    (workbench / "projects/demo/brief.md").write_text("# Changed research brief\n")
    assert "stale" in app.status().context_status
    with pytest.raises(FormatError, match="stale"):
        app.acknowledge(original.binding.token)
    new = app.refresh()
    assert new.binding.token != original.binding.token
    assert original.context_path.is_file()
    assert len(fake.sent) == 2
    with pytest.raises(FormatError, match="token"):
        app.acknowledge(original.binding.token)


def test_provider_replacement_does_not_reuse_acknowledgement(workbench, fake):
    app = workspace(workbench, fake)
    first = app.open()
    app.acknowledge(first.binding.token)
    sid = first.binding.session_id
    fake.sessions[sid] = replace(fake.sessions[sid], agent_session_id="native-b")
    assert "conversation changed" in app.status().context_status
    second = app.open()
    assert second.context_status == "submitted"
    assert second.binding.token != first.binding.token
    assert second.binding.provider_session_id == "native-b"
    assert len(fake.sent) == 2


def test_offline_state_does_not_construct_adapter(workbench, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline status must not access AoE")

    monkeypatch.setattr("toulmin.application.aoe.AoEClient", forbidden)
    assert AoEWorkspace(workbench, "demo").status(check_session=False).context_status == "unbound"


@pytest.mark.parametrize("name", ["context.md", "state.md", "manifest.json"])
def test_modified_context_is_rejected_instead_of_silently_repaired(workbench, fake, name):
    app = workspace(workbench, fake)
    first = app.open()
    first.context_path.with_name(name).write_text("altered\n")
    with pytest.raises(FormatError, match="context"):
        app.acknowledge(first.binding.token)
    with pytest.raises(FormatError, match="context"):
        app.refresh()
    assert len(fake.sent) == 1


def test_missing_receipt_does_not_report_acknowledged(workbench, fake):
    app = workspace(workbench, fake)
    view = app.open()
    app.acknowledge(view.binding.token)
    view.context_path.with_name("receipt.json").unlink()
    assert app.status(check_session=False).context_status == "invalid context"


def test_bind_refuses_other_path_and_cross_project_reuse(workbench, fake):
    fake.add_session()
    fake.sessions[SID] = replace(fake.sessions[SID], path=workbench.parent)
    with pytest.raises(FormatError, match="path"):
        workspace(workbench, fake).bind(SID)
    assert not (workbench / "projects/demo/.aoe").exists()
    fake.sessions[SID] = replace(fake.sessions[SID], path=workbench)
    workspace(workbench, fake).bind(SID)
    initialize(workbench, "other")
    with pytest.raises(FormatError, match="already bound"):
        AoEWorkspace(workbench, "other", fake).bind(SID)


@pytest.mark.parametrize("field,new", [("profile", "other"), ("tool", "claude")])
def test_binding_identity_changes_require_explicit_replacement(workbench, fake, field, new):
    fake.add_session()
    app = workspace(workbench, fake)
    first = app.bind(SID)
    if field == "profile":
        fake.profile = new
    else:
        fake.sessions[SID] = replace(fake.sessions[SID], tool=new)
    with pytest.raises(FormatError, match="replace"):
        app.bind(SID)
    updated = app.bind(SID, replace_existing=True)
    assert updated.binding.token != first.binding.token
    assert updated.binding.profile == fake.profile
    assert updated.binding.agent == fake.sessions[SID].tool


def test_corrupt_foreign_binding_refuses_session_reuse(workbench, fake):
    initialize(workbench, "other")
    path = workbench / "projects/other/.aoe"
    path.mkdir()
    (path / "binding.json").write_text("{}")
    fake.add_session()
    with pytest.raises(FormatError, match="invalid AoE binding"):
        workspace(workbench, fake).bind(SID)


def test_new_session_requires_explicit_request_and_preserves_old_archive(workbench, fake):
    app = workspace(workbench, fake)
    first = app.open()
    with pytest.raises(FormatError, match="live"):
        app.open(new_session=True)
    fake.sessions[first.binding.session_id] = replace(
        fake.sessions[first.binding.session_id], state="archived"
    )
    with pytest.raises(FormatError, match="not live"):
        app.open()
    second = app.open(new_session=True)
    assert second.binding.session_id != first.binding.session_id
    assert first.context_path.is_file()
    assert fake.created == 2


def test_missing_session_can_be_explicitly_replaced(workbench, fake):
    app = workspace(workbench, fake)
    app.open()
    fake.sessions.clear()
    with pytest.raises(AoEError):
        app.open()
    app.open(new_session=True)
    assert fake.created == 2


def test_symlink_binding_directory_cannot_redirect_writes(workbench, fake, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (workbench / "projects/demo/.aoe").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FormatError, match="symlinks"):
        workspace(workbench, fake).open()
    assert not list(outside.iterdir()) and fake.created == 0


def test_dispatch_does_not_cross_profile_or_send_superseded_context(workbench, fake):
    app = workspace(workbench, fake)
    fake.add_session()
    first = app.bind(SID)
    other = FakeAoE(workbench, "other")
    with pytest.raises(FormatError, match="profile"):
        app._dispatch(other, expected_token=first.binding.token)
    app._dispatch(fake, expected_token="old-token")
    assert not fake.sent and not other.sent


def test_moved_multi_project_workbench_can_rebind_each_project(workbench, fake, tmp_path):
    initialize(workbench, "other")
    fake.add_session()
    fake.add_session("other", "b" * 16)
    workspace(workbench, fake).bind(SID)
    AoEWorkspace(workbench, "other", fake).bind("b" * 16)
    moved = tmp_path / "moved"
    workbench.rename(moved)
    fake.root = moved
    fake.sessions = {sid: replace(session, path=moved) for sid, session in fake.sessions.items()}
    first = workspace(moved, fake).bind(SID, replace_existing=True)
    second = AoEWorkspace(moved, "other", fake).bind("b" * 16, replace_existing=True)
    assert first.binding.root == second.binding.root == str(moved)
    assert first.context_status == second.context_status == "prepared"


def test_edited_binding_identity_cannot_reuse_another_conversations_receipt(workbench, fake):
    app = workspace(workbench, fake)
    first = app.open()
    app.acknowledge(first.binding.token)
    path = workbench / "projects/demo/.aoe/binding.json"
    saved = json.loads(path.read_text())
    saved["provider_session_id"] = "native-b"
    path.write_text(json.dumps(saved))
    fake.sessions[first.binding.session_id] = replace(
        fake.sessions[first.binding.session_id], agent_session_id="native-b"
    )
    assert app.status().context_status == "invalid context"
