import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.cli.initialize import initialize
from toulmin.core.codec import decode, encode
from toulmin.protocols.status import project_status


def edit(root, relative, body=None, **values):
    path = root / "projects/demo" / relative
    document = decode(path.read_bytes())
    document.header.update(values)
    if body is not None:
        document.body = body
    path.write_bytes(encode(document))
    return document


def support(root, grade="verified", status="valid", direction="supports", target="C-001"):
    document = edit(
        root, "evidence/E-001.md", grade=grade, status=status, direction=direction, target=target
    )
    if grade == "verified":
        document.header["verification"] = {
            "method": "test fixture",
            "result": "fixture result",
            "artifacts": ["projects/demo/runs/20261031T100000Z-review/output.md"],
        }
    if status == "invalidated":
        document.body += "\n## Invalidation\nFixture evidence has been withdrawn.\n"
    (root / "projects/demo/evidence/E-001.md").write_bytes(encode(document))


def objection(root, severity="major", status="open"):
    edit(
        root,
        "objections/O-001.md",
        severity=severity,
        status=status,
        body=(
            "## Content\nFixture objection.\n\n## Response\nFixture response.\n\n"
            "## Ruling\nFixture ruling.\n"
        ),
    )


def run_status(root, project="demo"):
    return CliRunner().invoke(app, ["status", project, "--root", str(root)])


def snapshot(root):
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        key = str(path.relative_to(root))
        info = path.lstat()
        if path.is_symlink():
            result[key] = ("symlink", str(path.readlink()), info.st_mtime_ns)
        elif path.is_file():
            result[key] = ("file", path.read_bytes(), info.st_mtime_ns)
        else:
            result[key] = ("directory", info.st_mtime_ns)
    return result


def test_new_workbench_has_valid_empty_status(workbench):
    result = run_status(workbench)
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    for text in (
        "Project: demo",
        "Stage: explore",
        "Next step:",
        "Data: valid",
        "Claims: none",
        "Open objections: none",
    ):
        assert text in result.stdout


@pytest.mark.parametrize(
    "grade,status,direction,severity,objection_status,eligible,count,has_open",
    [
        ("model-asserted", "valid", "supports", "minor", "answered", False, 0, False),
        ("intuition", "valid", "supports", "minor", "answered", False, 0, False),
        ("verified", "valid", "refutes", "minor", "answered", False, 0, False),
        ("verified", "invalidated", "supports", "minor", "answered", False, 0, False),
        ("verified", "valid", "supports", "fatal", "open", False, 1, True),
        ("verified", "valid", "supports", "major", "open", False, 1, True),
        ("verified", "valid", "supports", "minor", "open", True, 1, True),
        ("verified", "valid", "supports", "major", "answered", True, 1, False),
        ("verified", "valid", "supports", "fatal", "deferred", True, 1, False),
    ],
)
def test_supported_conditions_use_valid_verified_support_and_open_objections(
    populated, grade, status, direction, severity, objection_status, eligible, count, has_open
):
    support(populated, grade, status, direction)
    objection(populated, severity, objection_status)
    result = run_status(populated)
    assert result.exit_code == 0, result.output
    claim = project_status(populated, "demo").claims[0]
    assert claim.eligible_for_supported is eligible
    assert claim.verified_support_count == count
    assert claim.has_open_objection is has_open
    assert claim.stored_status == "proposed"
    assert f"eligible_supported={'yes' if eligible else 'no'}" in result.stdout
    if eligible:
        assert "researcher decision pending" in result.stdout


@pytest.mark.parametrize("state", ["supported", "accepted"])
def test_lost_support_preserves_historical_state_and_reports_review(populated, state):
    support(populated, status="invalidated")
    objection(populated, status="answered")
    edit(populated, "claims/C-001.md", status=state, decisions=["D-001"])
    before = snapshot(populated)
    result = run_status(populated)
    assert result.exit_code == 0, result.output
    assert f"stored={state}" in result.stdout
    assert "does not meet supported conditions" in result.stdout
    assert "eligible_supported=no" in result.stdout
    assert snapshot(populated) == before


def test_minor_objection_and_supported_eligibility_are_both_shown(populated):
    support(populated)
    objection(populated, severity="minor")
    edit(populated, "claims/C-001.md", status="challenged")
    result = run_status(populated)
    assert result.exit_code == 0, result.output
    assert "stored=challenged" in result.stdout
    assert "open_objection=yes | eligible_supported=yes" in result.stdout
    assert "O-001 | minor" in result.stdout


def test_severity_and_numeric_id_order_is_deterministic(populated):
    objection(populated, severity="minor")
    path = populated / "projects/demo/objections/O-001.md"
    document = decode(path.read_bytes())
    for number, severity in [(1000, "major"), (2, "fatal"), (999, "major"), (10, "minor")]:
        document.header.update(id=f"O-{number:03d}", severity=severity)
        path.with_name(f"O-{number:03d}.md").write_bytes(encode(document))
    result = run_status(populated)
    assert result.exit_code == 0, result.output
    report = project_status(populated, "demo")
    assert [str(item.object_id) for item in report.open_objections] == [
        "O-002",
        "O-999",
        "O-1000",
        "O-001",
        "O-010",
    ]
    assert run_status(populated).stdout == result.stdout


def test_successful_status_preserves_entire_tree_bytes_and_mtimes(populated):
    before = snapshot(populated)
    assert run_status(populated).exit_code == 0
    assert snapshot(populated) == before


def test_dangling_target_marks_all_conditions_unknown_and_is_read_only(populated):
    support(populated)
    objection(populated, status="answered")
    edit(populated, "specs/S-001.md", target="C-999")
    before = snapshot(populated)
    result = run_status(populated)
    assert result.exit_code == 1
    assert "Data: INVALID" in result.stdout
    assert "S-001.md" in result.stderr and "target" in result.stderr
    assert "eligible_supported=unknown" in result.stdout
    assert "eligible_supported=yes" not in result.stdout
    assert snapshot(populated) == before


def test_duplicate_ids_and_filename_mismatches_are_reported(populated):
    source = populated / "projects/demo/claims/C-001.md"
    source.with_name("C-002.md").write_bytes(source.read_bytes())
    result = run_status(populated)
    assert result.exit_code == 1
    assert "duplicate ID C-001" in result.stderr
    assert "C-002.md" in result.stderr


def test_bad_objects_are_all_reported_instead_of_silently_skipped(populated):
    (populated / "projects/demo/evidence/E-002.md").write_text("broken YAML header")
    edit(populated, "objections/O-001.md", status="unknown")
    result = run_status(populated)
    assert result.exit_code == 1
    assert "E-002.md" in result.stderr
    assert "O-001.md" in result.stderr and "status" in result.stderr
    assert "INVALID" in result.stdout


def test_wrong_folder_and_noncanonical_filename_cannot_hide_objects(populated):
    source = populated / "projects/demo/claims/C-001.md"
    source.with_name("renamed.md").write_bytes(source.read_bytes())
    (populated / "projects/demo/objections/backup").mkdir()
    result = run_status(populated)
    assert result.exit_code == 1
    assert "renamed.md" in result.stderr
    assert "backup" in result.stderr


def test_raw_run_output_is_not_parsed_as_formal_objects(populated):
    archive = populated / "projects/demo/runs/20261031T100000Z-review"
    (archive / "raw.md").write_text("---\nid: an invalid draft\nThis is raw output.\n")
    assert run_status(populated).exit_code == 0


@pytest.mark.parametrize(
    "reference", ["[[C-999]]", "[[missing/C-001]]", "[[C-1]]", "[[../C-001]]", "[[]]", "[[C-001]"]
)
def test_brief_reference_errors_include_brief_line_and_bad_marker(populated, reference):
    (populated / "projects/demo/brief.md").write_text("# Brief\n\n" + reference + "\n")
    result = run_status(populated)
    assert result.exit_code == 1
    assert "brief.md:3: reference" in result.stderr


def test_brief_valid_references_and_fenced_or_indented_examples(populated):
    (populated / "projects/demo/brief.md").write_text(
        "# Brief\n[[C-001]] and [[demo/E-001]].\n"
        "````markdown\n[[C-999]]\n```\n[[C-998]]\n````\n"
        "~~~\n[[C-997]]\n~~~\n    [[C-996]]\n\t[[C-995]]\n"
    )
    result = run_status(populated)
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "field,value",
    [
        ("stage", "spec"),
        ("next_step", ""),
        ("recent_decisions", ["C-001"]),
        ("recent_decisions", ["D-999"]),
        ("last_handoff", "../escape.md"),
        ("last_handoff", "missing.md"),
        ("unknown", "field"),
    ],
)
def test_project_metadata_is_validated_without_repair(populated, field, value):
    edit(populated, "PROJECT.md", **{field: value})
    before = snapshot(populated)
    result = run_status(populated)
    assert result.exit_code == 1
    assert field in result.stderr
    assert snapshot(populated) == before


def test_oversized_or_incomplete_project_charter_is_reported_not_truncated(populated):
    path = populated / "projects/demo/PROJECT.md"
    original = path.read_text() + "extra context\n" * 40
    path.write_text(original)
    result = run_status(populated)
    assert result.exit_code == 1
    assert "40 lines" in result.stderr
    assert path.read_text() == original


def test_missing_project_parts_and_symlinks_fail_without_following_them(populated, tmp_path):
    folder = populated / "projects/demo/specs"
    (folder / "S-001.md").unlink()
    (folder / ".gitkeep").unlink()
    folder.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    folder.symlink_to(outside)
    result = run_status(populated)
    assert result.exit_code == 1
    assert "symlinks forbidden" in result.stderr
    assert list(outside.iterdir()) == []


def test_project_isolation_and_target_qualification(populated):
    initialize(populated, "other")
    original = (populated / "projects/demo/claims/C-001.md").read_bytes()
    (populated / "projects/other/claims/C-001.md").write_bytes(original)
    (populated / "projects/other/evidence/E-999.md").write_text("unrelated broken file")
    support(populated, target="other/C-001")
    objection(populated, status="answered")
    result = run_status(populated)
    assert result.exit_code == 0, result.output
    assert "verified_support=0" in result.stdout
    support(populated, target="demo/C-001")
    assert "verified_support=1" in run_status(populated).stdout
    (populated / "projects/demo/brief.md").write_text("[[other/C-001]]\n")
    assert run_status(populated).exit_code == 0
    assert run_status(populated, "other").exit_code == 1


def test_active_or_interrupted_writer_is_reported_without_touching_lock(populated):
    lock = populated / "projects/demo/.toulmin-new.lock"
    lock.mkdir()
    before = snapshot(populated)
    result = run_status(populated)
    assert result.exit_code == 1
    assert "active or interrupted writer" in result.stderr
    assert snapshot(populated) == before


def test_default_root_and_real_installed_command(populated, monkeypatch):
    monkeypatch.chdir(populated)
    result = CliRunner().invoke(app, ["status", "demo"])
    assert result.exit_code == 0, result.output
    command = Path(sys.executable).with_name("toulmin")
    process = subprocess.run(
        [str(command), "status", "demo"], capture_output=True, text=True, check=True
    )
    assert process.stdout == result.stdout and process.stderr == ""


def test_bad_project_name_and_missing_project_have_distinct_exit_codes(workbench):
    assert run_status(workbench, "../escape").exit_code == 2
    result = run_status(workbench, "missing")
    assert result.exit_code == 1
    assert "missing" in result.stderr
