"""WI2: L1 scope/charter models and L2 root classification, without the CLI."""

import pytest

from toulmin.cli.initialize import initialize, initialize_workspace, workspace_setup
from toulmin.core.codec import decode
from toulmin.core.scope import WORKSPACE, Scope
from toulmin.core.workspace import (
    NO_DIRECTION,
    render_initial,
    validate_charter,
    validate_name,
)
from toulmin.protocols.workspace_state import RootState, classify_root


def test_scope_round_trip_and_locations():
    child = Scope("scheduling")
    assert Scope.from_data(child.to_data()) == child
    assert Scope.from_data({"kind": "workspace"}) == WORKSPACE
    assert WORKSPACE.display == "Workspace" and child.display == "Project: scheduling"
    assert WORKSPACE.records("runs") == "runs"
    assert child.records("sessions") == "projects/scheduling/sessions"


@pytest.mark.parametrize(
    "value",
    [
        "workspace",
        {"kind": "project"},
        {"kind": "workspace", "project": "x"},
        {"kind": "project", "project": "Bad_Name"},
        {"kind": "global"},
    ],
)
def test_invalid_scopes_are_refused(value):
    with pytest.raises(ValueError):
        Scope.from_data(value)


@pytest.mark.parametrize("name", ["", " padded", "two\nlines", "x" * 81, "tab\there", "a b"])
def test_invalid_names_are_refused(name):
    with pytest.raises(ValueError):
        validate_name(name)


@pytest.mark.parametrize("name", ['Quote " and \\ back', "服务研究", "Serving: Research #1"])
def test_initial_charter_round_trips_any_allowed_name(name):
    charter = validate_charter(decode(render_initial(name)))
    assert charter.name == name
    assert charter.revision == 0 and charter.receipt is None
    assert charter.direction is None and charter.sections == ()
    assert charter.next_step is None and charter.last_handoff is None
    assert NO_DIRECTION in render_initial(name).decode()


def test_root_classification(tmp_path):
    setup = workspace_setup()
    assert classify_root(tmp_path / "absent", setup).state == RootState.MISSING
    empty = tmp_path / "empty"
    (empty / ".git").mkdir(parents=True)
    assert classify_root(empty, setup).state == RootState.EMPTY
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace)
    assert classify_root(workspace, setup).state == RootState.WORKSPACE
    (workspace / "WORKSPACE.md").unlink()
    assert classify_root(workspace, setup).state == RootState.INCOMPLETE
    legacy = tmp_path / "legacy"
    initialize(legacy, "demo")
    assert classify_root(legacy, setup).state == RootState.LEGACY
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "notes.txt").write_text("x\n")
    report = classify_root(unrelated, setup)
    assert report.state == RootState.UNRELATED and report.unexpected == ("notes.txt",)


def test_classification_reports_init_remnants_without_trusting_them(tmp_path):
    root = tmp_path / "workspace"
    initialize_workspace(root)
    (root / "WORKSPACE.md").unlink()
    (root / ".toulmin-init-abc").mkdir()
    report = classify_root(root, workspace_setup())
    assert report.state == RootState.INCOMPLETE
    assert report.remnants == (".toulmin-init-abc",)
