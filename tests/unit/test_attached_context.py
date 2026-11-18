"""Attached startup recovery uses fake native sessions and never consumes model quota."""

import threading
from dataclasses import replace

import pytest

from tests.unit.test_aoe_workspace import FakeAoE
from toulmin.application import attached_context
from toulmin.application.aoe import AoEWorkspace
from toulmin.core.documents import FormatError


@pytest.fixture(autouse=True)
def quick_watch(monkeypatch):
    monkeypatch.setattr(attached_context, "POLL_SECONDS", 0.002)
    monkeypatch.setattr(attached_context, "TIMEOUT_SECONDS", 2.0)


def prepared(root):
    client = FakeAoE(root)
    client.add_session()
    client.is_ready = False
    service = AoEWorkspace(root, "demo", client)
    return service, client, service.bind()


def finish(watch):
    assert watch.thread is not None
    watch.thread.join(timeout=5)
    assert not watch.thread.is_alive()


def test_native_menu_then_ready_automatically_delivers_once(workbench):
    service, client, view = prepared(workbench)
    observations = []

    def ready(session):
        observations.append(session)
        return len(observations) >= 3, "menu until researcher resolves it"

    client.ready = ready
    with attached_context.AttachedContext(service, client, view) as watch:
        finish(watch)
    assert len(observations) >= 3
    assert len(client.sent) == 1
    assert "context-read receipt" in client.sent[0][1]
    assert watch.latest.binding.delivery == "submitted"
    assert service.bound_session().delivery == "submitted"  # No receipt is fabricated.


@pytest.mark.parametrize("delivery", ["sending", "submitted", "uncertain", "acknowledged"])
def test_submitted_uncertain_or_acknowledged_context_is_never_retried(workbench, delivery):
    service, client, view = prepared(workbench)
    view = replace(view, binding=replace(view.binding, delivery=delivery))
    with attached_context.AttachedContext(service, client, view) as watch:
        assert watch.thread is None
    assert not client.sent


def test_busy_or_typed_input_times_out_without_submission(workbench, monkeypatch):
    service, client, view = prepared(workbench)
    monkeypatch.setattr(attached_context, "TIMEOUT_SECONDS", 0.03)
    with attached_context.AttachedContext(service, client, view) as watch:
        finish(watch)
    assert not client.sent and watch.latest is None
    assert service.bound_session().delivery == "prepared"


def test_detach_during_readiness_cancels_before_any_refresh(workbench):
    service, client, view = prepared(workbench)
    checking, release = threading.Event(), threading.Event()

    def ready(session):
        checking.set()
        assert release.wait(3)
        return True, "now ready"

    client.ready = ready
    with attached_context.AttachedContext(service, client, view) as watch:
        assert checking.wait(2)
    release.set()
    finish(watch)
    assert not client.sent
    assert service.bound_session().delivery == "prepared"


def test_detach_during_dispatch_revalidation_cancels_before_sending(workbench):
    service, client, view = prepared(workbench)
    checking, release = threading.Event(), threading.Event()
    count = 0

    def ready(session):
        nonlocal count
        count += 1
        if count == 2:
            checking.set()
            assert release.wait(3)
        return True, "ready after observation"

    client.ready = ready
    with attached_context.AttachedContext(service, client, view) as watch:
        assert checking.wait(2)
    release.set()
    finish(watch)
    assert not client.sent
    assert service.bound_session().delivery == "prepared"


@pytest.mark.parametrize("change", ["session_id", "profile", "token", "delivery"])
def test_guarded_refresh_refuses_changed_binding_without_writes(workbench, change):
    service, client, view = prepared(workbench)
    expected = replace(view.binding, **{change: "0" * 32 if change != "delivery" else "submitted"})
    before = {p: p.read_bytes() for p in workbench.rglob("*") if p.is_file()}
    with pytest.raises(FormatError, match="automatic delivery stopped"):
        service.refresh(expected=expected)
    assert not client.sent
    assert {p: p.read_bytes() for p in workbench.rglob("*") if p.is_file()} == before


def test_another_operation_submitting_between_checks_is_not_resent(workbench):
    service, client, view = prepared(workbench)

    def ready(session):
        service._save(replace(view.binding, delivery="submitted"))
        return True, "another operator sent it"

    client.ready = ready
    with attached_context.AttachedContext(service, client, view) as watch:
        finish(watch)
    assert not client.sent
    assert service.bound_session().delivery == "submitted"


def test_transient_dispatch_readiness_loss_retries_only_prepared_context(workbench):
    service, client, view = prepared(workbench)
    count = 0

    def ready(session):
        nonlocal count
        count += 1
        return count != 2, "UI changes between watcher and dispatch checks"

    client.ready = ready
    with attached_context.AttachedContext(service, client, view) as watch:
        finish(watch)
    assert count >= 4
    assert len(client.sent) == 1
    assert watch.latest.binding.delivery == "submitted"
