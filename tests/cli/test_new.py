import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.cli.initialize import initialize
from toulmin.core import repository as storage
from toulmin.core.codec import decode, encode
from toulmin.core.documents import DIRECTORIES, STATUSES, Document
from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.schema import validate


def draft_file(root, example, name="draft.md"):
    header = deepcopy(example.header)
    for key in ("id", "created", "confirmed_by"):
        header.pop(key)
    if example.object_id.kind != ObjectKind.RUN:
        header.pop("status")
    document = Document(header, example.body)
    directory = root / "projects/demo/runs/manual-intake"
    directory.mkdir(exist_ok=True)
    path = directory / name
    path.write_bytes(encode(document))
    return path, document


def arguments(root, kind, path, project="demo", confirm=True):
    return [
        "new",
        str(kind),
        project,
        "--root",
        str(root),
        "--input",
        str(path.relative_to(root)),
        "--confirmed-by",
        "Tianchi YU",
    ] + (["--confirm"] if confirm else [])


def files(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("kind", list(ObjectKind))
def test_new_creates_each_type_with_canonical_header_and_body(populated, example_docs, kind):
    path, draft = draft_file(populated, example_docs[kind])
    original = path.read_bytes()
    result = CliRunner().invoke(app, arguments(populated, kind, path))
    assert result.exit_code == 0, result.output
    target = populated / "projects/demo" / DIRECTORIES[kind] / f"{ObjectId(kind, 2)}.md"
    assert result.stdout == f"{target.relative_to(populated)}\n"
    document = decode(target.read_bytes())
    validate(document)
    Repository(populated).validate_links(document, "demo")
    assert document.object_id == ObjectId(kind, 2)
    assert document.header["status"] == STATUSES[kind][0]
    assert document.header["confirmed_by"]["actor"] == "Tianchi YU"
    assert document.header["confirmed_by"]["at"].endswith("Z")
    assert document.body == draft.body
    assert path.read_bytes() == original
    assert not list((populated / "projects/demo").glob(".toulmin-new.lock"))


def test_unconfirmed_draft_stays_archived_without_any_writes(populated, example_docs):
    path, _ = draft_file(populated, example_docs[ObjectKind.OBJECTION])
    before = files(populated)
    result = CliRunner().invoke(
        app, arguments(populated, ObjectKind.OBJECTION, path, confirm=False)
    )
    assert result.exit_code == 1
    assert "explicit researcher confirmation" in result.stderr
    assert result.stdout == ""
    assert files(populated) == before


def test_model_provenance_traces_back_through_run_to_original_output(populated, example_docs):
    path, _ = draft_file(populated, example_docs[ObjectKind.OBJECTION])
    result = CliRunner().invoke(app, arguments(populated, ObjectKind.OBJECTION, path))
    assert result.exit_code == 0
    repository = Repository(populated)
    objection = repository.load("demo", ObjectId(ObjectKind.OBJECTION, 2))
    run, project = repository.resolve("demo", objection.header["source"]["ref"])
    assert project == "demo" and run.header["model"] == "example-model"
    original = repository.path(objection.header["source"]["path"], "file")
    assert original.is_relative_to(repository.path(run.header["output"], "directory"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "accepted"),
        ("id", "C-999"),
        ("created", "2026-10-31T00:00:00Z"),
        ("confirmed_by", {"actor": "AI", "at": "2026-10-31T00:00:00Z"}),
        ("schema_version", 2),
        ("type", "workload"),
        ("source", {}),
    ],
)
def test_bad_draft_cannot_override_generated_fields_or_initial_status(
    populated, example_docs, field, value
):
    path, draft = draft_file(populated, example_docs[ObjectKind.CLAIM])
    draft.header[field] = value
    path.write_bytes(encode(draft))
    before = files(populated)
    result = CliRunner().invoke(app, arguments(populated, ObjectKind.CLAIM, path))
    assert result.exit_code == 1
    assert field in result.stderr
    assert files(populated) == before
    assert not (populated / "projects/demo/.toulmin-new.lock").exists()


def test_run_outcome_is_required_instead_of_assuming_success(populated, example_docs):
    path, draft = draft_file(populated, example_docs[ObjectKind.RUN])
    draft.header.pop("status")
    path.write_bytes(encode(draft))
    result = CliRunner().invoke(app, arguments(populated, ObjectKind.RUN, path))
    assert result.exit_code == 1
    assert "explicitly completed or failed" in result.stderr


def test_failed_run_is_preserved_with_failure_reason(populated, example_docs):
    path, draft = draft_file(populated, example_docs[ObjectKind.RUN])
    draft.header["status"] = "failed"
    draft.body += "\n## Failure\nTest fixture: manual run failed before completing the review.\n"
    path.write_bytes(encode(draft))
    result = CliRunner().invoke(app, arguments(populated, ObjectKind.RUN, path))
    assert result.exit_code == 0, result.output
    run = Repository(populated).load("demo", ObjectId(ObjectKind.RUN, 2))
    assert run.header["status"] == "failed" and "## Failure" in run.body


def test_cross_project_reference_and_per_project_numbering(populated, example_docs):
    initialize(populated, "second")
    claim_path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    result = CliRunner().invoke(
        app, arguments(populated, ObjectKind.CLAIM, claim_path, project="second")
    )
    assert result.exit_code == 0, result.output
    assert (populated / "projects/second/claims/C-001.md").exists()
    objection_path, objection = draft_file(populated, example_docs[ObjectKind.OBJECTION])
    objection.header["target"] = "second/C-001"
    objection_path.write_bytes(encode(objection))
    assert (
        CliRunner()
        .invoke(app, arguments(populated, ObjectKind.OBJECTION, objection_path))
        .exit_code
        == 0
    )
    assert (
        Repository(populated).load("demo", ObjectId(ObjectKind.OBJECTION, 2)).header["target"]
        == "second/C-001"
    )


def test_replaying_draft_allocates_a_new_id_without_changing_old_objects(populated, example_docs):
    path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    command = arguments(populated, ObjectKind.CLAIM, path)
    assert CliRunner().invoke(app, command).exit_code == 0
    existing = (populated / "projects/demo/claims/C-002.md").read_bytes()
    assert CliRunner().invoke(app, command).exit_code == 0
    assert (populated / "projects/demo/claims/C-002.md").read_bytes() == existing
    assert (populated / "projects/demo/claims/C-003.md").is_file()


def test_missing_or_mismatched_existing_ids_are_not_silently_reused(populated, example_docs):
    path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    directory = populated / "projects/demo/claims"
    (directory / "C-004.md").write_bytes((directory / "C-001.md").read_bytes())
    result = CliRunner().invoke(app, arguments(populated, ObjectKind.CLAIM, path))
    assert result.exit_code == 1
    assert "does not match filename" in result.stderr
    assert not (directory / "C-005.md").exists()


@pytest.mark.parametrize(
    "bad_path", ["../outside.md", "/absolute/draft.md", "projects/../draft.md", "a\\b.md"]
)
def test_input_paths_cannot_escape_workbench(populated, bad_path):
    command = [
        "new",
        "claim",
        "demo",
        "--root",
        str(populated),
        "--input",
        bad_path,
        "--confirmed-by",
        "X",
        "--confirm",
    ]
    before = files(populated)
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 1
    assert files(populated) == before


def test_symlinked_input_and_target_directory_are_rejected(populated, example_docs, tmp_path):
    path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = path.parent / "alias.md"
    alias.symlink_to(path)
    assert CliRunner().invoke(app, arguments(populated, ObjectKind.CLAIM, alias)).exit_code == 1
    claims = populated / "projects/demo/claims"
    claims.rename(populated / "saved-claims")
    claims.symlink_to(outside)
    assert CliRunner().invoke(app, arguments(populated, ObjectKind.CLAIM, path)).exit_code == 1
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("operation", ["link", "fsync"])
def test_publication_failures_leave_no_half_object_or_temporary_file(
    populated, example_docs, monkeypatch, operation
):
    path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    before = files(populated)

    def fail(*args, **kwargs):
        raise OSError("injected disk failure")

    monkeypatch.setattr(storage.os, operation, fail)
    result = CliRunner().invoke(app, arguments(populated, ObjectKind.CLAIM, path))
    assert result.exit_code == 1
    assert "injected disk failure" in result.stderr
    assert files(populated) == before
    assert not list((populated / "projects/demo/claims").glob(".new-*"))
    assert not (populated / "projects/demo/.toulmin-new.lock").exists()


def test_exclusive_publish_never_overwrites_a_claim(populated, example_docs, monkeypatch):
    path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    before = files(populated)
    monkeypatch.setattr(Repository, "next_id", lambda *args: ObjectId(ObjectKind.CLAIM, 1))
    assert CliRunner().invoke(app, arguments(populated, ObjectKind.CLAIM, path)).exit_code == 1
    assert files(populated) == before


def test_two_independent_processes_cannot_allocate_the_same_id(populated, example_docs):
    path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    command = [
        str(Path(sys.executable).with_name("toulmin")),
        *arguments(populated, ObjectKind.CLAIM, path),
    ]
    processes = [
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    outputs = [process.communicate(timeout=20) for process in processes]
    assert any(process.returncode == 0 for process in processes)
    for process, (_stdout, stderr) in zip(processes, outputs, strict=True):
        if process.returncode:
            assert process.returncode == 1 and "holds the lock" in stderr
            subprocess.run(command, capture_output=True, text=True, check=True)
    repository = Repository(populated)
    assert repository.load("demo", ObjectId(ObjectKind.CLAIM, 2)).object_id.number == 2
    assert repository.load("demo", ObjectId(ObjectKind.CLAIM, 3)).object_id.number == 3


def test_stale_lock_reports_problem_without_removing_it(populated, example_docs):
    path, _ = draft_file(populated, example_docs[ObjectKind.CLAIM])
    lock = populated / "projects/demo/.toulmin-new.lock"
    lock.mkdir()
    result = CliRunner().invoke(app, arguments(populated, ObjectKind.CLAIM, path))
    assert result.exit_code == 1
    assert "holds the lock" in result.stderr
    assert lock.is_dir()
