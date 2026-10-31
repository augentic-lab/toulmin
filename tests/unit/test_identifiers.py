import pytest

from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef, validate_project_name
from toulmin.protocols.session import entry_files


@pytest.mark.parametrize("prefix,kind", list(zip("CEODXSR", ObjectKind, strict=True)))
def test_object_ids_are_canonical(prefix, kind):
    assert ObjectId.parse(f"{prefix}-001") == ObjectId(kind, 1)
    assert str(ObjectId(kind, 1000)) == f"{prefix}-1000"


@pytest.mark.parametrize(
    "value", ["C-0", "C-000", "C-1", "C-0001", "C-01", "C--001", "c-001", "Z-001", "C-001\n"]
)
def test_invalid_ids_are_rejected(value):
    with pytest.raises(ValueError):
        ObjectId.parse(value)


@pytest.mark.parametrize("number", [0, -1, True, 1.5, "1"])
def test_numbers_are_positive_integers(number):
    with pytest.raises(ValueError):
        ObjectId(ObjectKind.CLAIM, number)


@pytest.mark.parametrize("value", ["C-001", "tail-latency/C-1000"])
def test_references_round_trip(value):
    assert str(ObjectRef.parse(value)) == value


@pytest.mark.parametrize(
    "value", ["../C-001", "/C-001", "a/b/C-001", "a\\b/C-001", "Upper/C-001", "demo/C-1"]
)
def test_references_cannot_encode_path_traversal(value):
    with pytest.raises(ValueError):
        ObjectRef.parse(value)


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "-demo", "demo-", "a--b", "demo\n"])
def test_invalid_project_names(name):
    with pytest.raises(ValueError):
        validate_project_name(name)


def test_entry_protocol_selects_resident_files_in_order():
    assert [str(path) for path in entry_files("demo", "2026-10-31-session.md")] == [
        "AGENTS.md",
        "projects/demo/PROJECT.md",
        "projects/demo/sessions/2026-10-31-session.md",
    ]
    assert len(entry_files("demo")) == 2


@pytest.mark.parametrize("handoff", ["../x.md", "/x.md", "a\\x.md", "x.txt", ".md", "x\n.md"])
def test_entry_protocol_rejects_handoffs_outside_sessions(handoff):
    with pytest.raises(ValueError):
        entry_files("demo", handoff)
